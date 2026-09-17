"""Geliştirme çalıştırıcısının saf mantığı: backoff, eski süreç tespiti, port denetimi."""

import socket
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from marketpulse.collectors.orderflow_ws import streams_for
from marketpulse.collectors.ws_stream import combined_url
from marketpulse.devtools import runner as runner_module
from marketpulse.devtools.procs import (
    RESTART_CAP_SEC,
    RunningProcess,
    ancestor_pids,
    backoff_delay,
    describe_pids,
    find_own_processes,
    is_own_process,
    parse_lsof_pids,
    parse_ps_output,
    parse_ps_parents,
    port_is_busy,
)
from marketpulse.devtools.runner import ProcessSpec, Supervisor
from marketpulse.devtools.wscheck import probe_urls, probe_verdict, progress_line, report

REPO = "/home/user/sketch"


def test_backoff_doubles_and_caps() -> None:
    assert backoff_delay(0) == 0.0
    assert [backoff_delay(n) for n in range(1, 6)] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert backoff_delay(20) == RESTART_CAP_SEC


def test_parse_ps_output() -> None:
    text = "  123 python -m marketpulse.engine\n  456 npm run dev\nbozuk satır\n   \n"
    processes = parse_ps_output(text)
    assert processes == [
        RunningProcess(123, "python -m marketpulse.engine"),
        RunningProcess(456, "npm run dev"),
    ]


@pytest.mark.parametrize(
    "command",
    [
        "/repo/backend/.venv/bin/python -m marketpulse.engine",
        "python -m uvicorn marketpulse.api.app:create_app --factory",
        "python -m marketpulse.devtools.runner",
        "node /home/user/sketch/frontend/node_modules/.bin/vite",
        # uvicorn --reload'un asıl sunucu çocuğu: komut satırında paket adı geçmez, yalnızca
        # bu deponun venv python'u görünür. Tanınmazsa 8000 portunu tutmaya devam ediyordu.
        (
            "/home/user/sketch/backend/.venv/bin/python -c "
            "from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=7)"
        ),
    ],
)
def test_recognises_own_processes(command: str) -> None:
    assert is_own_process(command, REPO)


@pytest.mark.parametrize(
    "command",
    [
        "node /other/project/node_modules/.bin/vite",  # başka projenin Vite'ı
        "postgres -D /var/lib/postgresql",
        "python -m http.server 3000",
        "npm --prefix /somewhere/else run dev",
        # Kullanıcının kendi kabuğu ve `make`: depo yolunu taşısalar bile asla öldürülmez.
        "/bin/bash -c source /home/user/sketch/.venv/bin/activate && npm run dev",
        "-zsh",
        "make dev",
    ],
)
def test_leaves_foreign_processes_alone(command: str) -> None:
    assert not is_own_process(command, REPO)


def test_find_own_processes_excludes_self() -> None:
    ps_text = "\n".join(
        [
            "10 python -m marketpulse.engine",
            "11 python -m marketpulse.devtools.runner",
            "12 node /other/project/vite",
        ]
    )
    found = find_own_processes(REPO, exclude_pids={11}, ps_text=ps_text)
    assert [p.pid for p in found] == [10]


def test_port_is_busy_detects_a_listening_socket() -> None:
    """Dolu port bind denemesiyle anlaşılır; süreçler arası bağlanma denemesi güvenilir değil."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert port_is_busy(port)
    finally:
        server.close()
    assert not port_is_busy(port)


def test_supervisor_restarts_a_crashing_process_without_touching_others() -> None:
    """Çöken süreç yeniden başlar; sağlıklı süreç etkilenmez."""
    lines: list[str] = []
    supervisor = Supervisor(
        [
            ProcessSpec("crasher", [sys.executable, "-c", "raise SystemExit(3)"]),
            ProcessSpec("steady", [sys.executable, "-c", "import time; time.sleep(30)"]),
        ],
        write=lines.append,
    )
    thread = threading.Thread(target=supervisor.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        if sum(1 for line in lines if line.startswith("crasher") and "başladı" in line) >= 2:
            break
        time.sleep(0.2)
    supervisor.request_stop()
    thread.join(timeout=20)

    crasher_starts = [line for line in lines if line.startswith("crasher") and "başladı" in line]
    steady_starts = [line for line in lines if line.startswith("steady") and "başladı" in line]
    assert len(crasher_starts) >= 2, lines  # en az bir kez yeniden başladı
    assert len(steady_starts) == 1  # sağlam süreç yeniden başlatılmadı
    assert any("çıkış kodu 3" in line for line in lines)
    assert any("Diğer süreçler çalışmaya devam ediyor" in line for line in lines)


def test_parse_lsof_pids_keeps_unique_numbers_only() -> None:
    assert parse_lsof_pids("  4321\n4321\n\nbozuk\n99\n") == [4321, 99]


def test_describe_pids_returns_commands_for_wanted_pids() -> None:
    ps_text = "10 python -m marketpulse.engine\n11 postgres -D /var/lib/postgresql"
    assert describe_pids([11, 12], ps_text=ps_text) == [
        RunningProcess(11, "postgres -D /var/lib/postgresql")
    ]


def test_free_own_ports_kills_our_port_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eski yığının port tutan sürecini durdurur; sahibi bizsek `make dev` durmamalı."""
    killed: list[int] = []
    owner = f"{runner_module.REPO_ROOT}/backend/.venv/bin/python -c spawn_main"
    monkeypatch.setattr(runner_module, "port_listener_pids", lambda _port: [4321])
    monkeypatch.setattr(runner_module, "describe_pids", lambda _pids: [RunningProcess(4321, owner)])
    monkeypatch.setattr(runner_module, "_terminate", lambda pid, force=False: killed.append(pid))
    monkeypatch.setattr(runner_module, "wait_for_ports_free", lambda timeout=0.0: [])

    assert runner_module.free_own_ports([8000]) == []
    assert killed == [4321]


def test_free_own_ports_never_kills_a_foreign_program(monkeypatch: pytest.MonkeyPatch) -> None:
    killed: list[int] = []
    monkeypatch.setattr(runner_module, "port_listener_pids", lambda _port: [777])
    monkeypatch.setattr(
        runner_module, "describe_pids", lambda _pids: [RunningProcess(777, "postgres -D /var/lib")]
    )
    monkeypatch.setattr(runner_module, "_terminate", lambda pid, force=False: killed.append(pid))
    monkeypatch.setattr(runner_module, "wait_for_ports_free", lambda timeout=0.0: [8000])

    assert runner_module.free_own_ports([8000]) == [8000]
    assert killed == []


def test_wait_for_ports_free_gives_the_port_time_to_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Öldürülen süreç portu hemen bırakmaz; ilk bakışta dolu görmek hata değildir."""
    answers = iter([[8000], [8000], []])
    monkeypatch.setattr(runner_module, "check_ports", lambda: next(answers, []))
    monkeypatch.setattr(runner_module, "PORT_POLL_SEC", 0.01)

    assert runner_module.wait_for_ports_free(timeout=2.0) == []


def test_ancestor_chain_covers_make_and_the_users_shell() -> None:
    """`make dev-stop` kendi kabuğunu öldürmemeli: ata zinciri listeden çıkarılır."""
    parents = parse_ps_parents("100 1\n200 100\n300 200\n999 1\n")
    assert ancestor_pids(300, parents) == {300, 200, 100, 1}
    assert 999 not in ancestor_pids(300, parents)


def test_ancestor_chain_survives_a_pid_loop() -> None:
    assert ancestor_pids(5, {5: 6, 6: 5}) == {5, 6}


class TestWsCheck:
    """Teşhis aracı engine ile **aynı** URL'ye bağlanmalı; yoksa ölçtüğü şey başka olur (F3-11)."""

    def test_it_listens_to_the_same_streams_the_engine_subscribes_to(self) -> None:
        url = combined_url("wss://fstream.binance.com/stream", streams_for(["BTCUSDT"]))

        assert url == (
            "wss://fstream.binance.com/stream?streams="
            "btcusdt@aggTrade/btcusdt@forceOrder/btcusdt@depth20@100ms"
        )

    async def test_the_report_names_a_stream_that_never_arrived(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Order book geliyor, işlem gelmiyor: canlıda görülen tablo.
        report(
            Counter({"btcusdt@depth20@100ms": 120}),
            Counter({"depthUpdate": 120}),
            None,
        )

        out = capsys.readouterr().out
        assert "aggTrade hiç gelmedi" in out
        assert "forceOrder hiç gelmedi" in out
        assert "İşlem mesajı hiç gelmedi" in out

    def test_the_probes_cover_the_candidate_spellings(self) -> None:
        """Üç aday: olduğu gibi, tamamen küçük harf, tek akış ucu."""
        urls = [probe.url for probe in probe_urls("wss://fstream.binance.com/stream", "BTCUSDT")]

        assert urls == [
            "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade",
            "wss://fstream.binance.com/stream?streams=btcusdt@aggtrade",
            "wss://fstream.binance.com/ws/btcusdt@aggTrade",
        ]

    def test_the_verdict_names_the_spelling_that_worked(self) -> None:
        verdict = probe_verdict([("olduğu gibi", 0), ("küçük harf", 412), ("tek akış", -1)])

        assert "küçük harf" in verdict
        assert "olduğu gibi" not in verdict

    def test_the_verdict_does_not_blame_the_spelling_when_none_worked(self) -> None:
        """Hiçbiri veri vermediyse sebep ad değildir; araç uydurmaz."""
        verdict = probe_verdict([("a", 0), ("b", 0), ("c", 0)])

        assert "akış adında değil" in verdict

    def test_the_progress_line_answers_the_question_on_its_own(self) -> None:
        """Kullanıcı 30 saniyeyi beklemeden kesse bile ara satır cevabı taşımalı."""
        line = progress_line(10.0, Counter({"depthUpdate": 1840}))

        assert "10 sn" in line
        assert "aggTrade 0" in line  # sıfır da yazılır: eksik olan görünür olsun
        assert "depthUpdate 1840" in line


class TestMakefileUsesTheSourcePath:
    """Backend komutları venv'deki kuruluma güvenmemeli.

    Bu hata iki kez ısırdı (`make dev-stop`, sonra `make wscheck`): venv'deki editable kurulum
    eskiyince `python -m marketpulse...` "No module named marketpulse" diyor. Çözüm her komutun
    başına `PYTHONPATH=backend/src` koymak; bu test yenisi eklenince unutulmasını engeller.
    """

    def _makefile(self, repo_root: Path) -> list[str]:
        return (repo_root / "Makefile").read_text(encoding="utf-8").splitlines()

    def test_no_backend_python_call_runs_without_pythonpath(self, repo_root: Path) -> None:
        offenders = [
            line.strip()
            for line in self._makefile(repo_root)
            if "backend/.venv/bin/python" in line
            and "PYTHONPATH=backend/src" not in line
            and "$(BACKEND_PY)" not in line
            and not line.lstrip().startswith("#")
            and "test -x" not in line  # yalnızca varlık denetimi, çalıştırma değil
        ]
        assert offenders == [], f"PYTHONPATH'siz backend çağrısı: {offenders}"

    def test_alembic_also_sees_the_package(self, repo_root: Path) -> None:
        """Alembic'in env.py'si `marketpulse` modellerini import eder; o da kaynağı görmeli."""
        alembic_lines = [line for line in self._makefile(repo_root) if "bin/alembic" in line]
        assert alembic_lines, "alembic çağrısı bulunamadı"
        assert all("PYTHONPATH=backend/src" in line for line in alembic_lines)
