"""Geliştirme çalıştırıcısının saf mantığı: backoff, eski süreç tespiti, port denetimi."""

import socket
import sys
import threading
import time

import pytest

from marketpulse.devtools.procs import (
    RESTART_CAP_SEC,
    RunningProcess,
    backoff_delay,
    find_own_processes,
    is_own_process,
    parse_ps_output,
    port_is_busy,
)
from marketpulse.devtools.runner import ProcessSpec, Supervisor

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
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepting = threading.Thread(target=lambda: _accept_once(server), daemon=True)
    accepting.start()
    try:
        assert port_is_busy(port)
    finally:
        server.close()
    assert not port_is_busy(port)


def _accept_once(server: socket.socket) -> None:
    try:
        connection, _ = server.accept()
        connection.close()
    except OSError:
        return


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
