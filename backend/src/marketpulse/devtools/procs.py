"""Süreç yardımcıları: backoff, eski süreç tespiti, port denetimi.

Saf fonksiyonlar burada tutulur ki test edilebilsinler; süreç başlatma `runner.py` içindedir.
"""

import socket
import subprocess
from dataclasses import dataclass

RESTART_BASE_SEC = 1.0
RESTART_CAP_SEC = 30.0
HEALTHY_RUN_SEC = 60.0
PS_TIMEOUT_SEC = 5.0
LSOF_TIMEOUT_SEC = 5.0

# Bize ait süreçleri tanımak için komut satırı imzaları. Yalnızca bu desenlere uyanlar durdurulur;
# 8000/3000 portunu tutan yabancı bir süreç asla öldürülmez, kullanıcıya bildirilir.
OWN_PROCESS_PATTERNS: tuple[str, ...] = (
    "marketpulse.engine",
    "marketpulse.api.app",
    "marketpulse.devtools.runner",
    "marketpulse.backfill",
)
# Arayüz süreci: yalnızca bu deponun frontend klasöründe çalışan Vite sayılır.
FRONTEND_MARKERS: tuple[str, ...] = ("vite", "npm")
# Kabuk ve make satırları asla süreç sayılmaz: kullanıcının terminali ya da `make dev`in kendisi
# depo yolunu komut satırında taşıyabilir; bunları öldürmek oturumu kapatır.
NEVER_KILL_BASENAMES: frozenset[str] = frozenset(
    {"bash", "sh", "zsh", "fish", "dash", "make", "gmake", "ssh", "tmux", "screen", "login"}
)


@dataclass(frozen=True)
class RunningProcess:
    pid: int
    command: str


def backoff_delay(restarts: int) -> float:
    """Yeniden başlatma gecikmesi: 1, 2, 4, 8 … en fazla 30 saniye."""
    if restarts <= 0:
        return 0.0
    return min(RESTART_CAP_SEC, RESTART_BASE_SEC * (2.0 ** (restarts - 1)))


def parse_ps_output(text: str) -> list[RunningProcess]:
    """`ps -eo pid=,command=` çıktısını ayrıştırır (macOS ve Linux'ta aynı biçim)."""
    processes: list[RunningProcess] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not pid_text.isdigit() or not command.strip():
            continue
        processes.append(RunningProcess(pid=int(pid_text), command=command.strip()))
    return processes


def is_own_process(command: str, repo_root: str) -> bool:
    """Komut satırı bu depoya ait bir MarketPulse süreci mi?

    Backend süreçleri paket adıyla tanınır. Arayüz süreci yalnızca bu deponun `frontend` yolunu
    içeriyorsa sayılır; başka bir projenin Vite sunucusu asla dokunulmaz. Kabuk ve `make` satırları
    hiçbir koşulda sayılmaz.
    """
    if _basename(command) in NEVER_KILL_BASENAMES:
        return False
    if any(pattern in command for pattern in OWN_PROCESS_PATTERNS):
        return True
    # uvicorn --reload asıl sunucuyu komut satırında paket adı geçmeyen bir çocukta çalıştırır
    # (multiprocessing spawn). O çocuk bu deponun venv python'u ile koşar; venv yalnızca bu depoya
    # aittir, bu yüzden yolu güvenli bir imzadır. Tanınmazsa 8000 portunu tutmaya devam ediyordu.
    if f"{repo_root}/backend/.venv/" in command:
        return True
    in_this_repo = repo_root in command or f"{repo_root}/frontend" in command
    return in_this_repo and any(marker in command for marker in FRONTEND_MARKERS)


def find_own_processes(
    repo_root: str, *, exclude_pids: set[int], ps_text: str | None = None
) -> list[RunningProcess]:
    """Bu depoya ait, hâlâ çalışan süreçler (kendimiz ve çocuklarımız hariç)."""
    text = ps_text if ps_text is not None else _run_ps()
    return [
        process
        for process in parse_ps_output(text)
        if process.pid not in exclude_pids and is_own_process(process.command, repo_root)
    ]


PROBE_HOSTS: tuple[str, ...] = ("0.0.0.0", "127.0.0.1")


def port_is_busy(port: int, hosts: tuple[str, ...] = PROBE_HOSTS) -> bool:
    """Port başka bir süreç tarafından tutuluyor mu?

    Ölçüm bağlanarak değil, **bağlanmayı deneyerek** (bind) yapılır: bazı ortamlarda loopback'e
    bağlanma denemesi dinleyen bir sunucuyu göremiyor, bind denemesi ise doğrudan çekirdeğe sorar.
    `SO_REUSEADDR` açık: yeni kapanmış bir sunucudan kalan TIME_WAIT soketleri "dolu" sayılmaz,
    canlı bir dinleyici ise yine `EADDRINUSE` verir. Hem `0.0.0.0` hem `127.0.0.1` denenir; süreçler
    farklı arayüzlere bağlanabiliyor (uvicorn 0.0.0.0, Vite yalnızca loopback).
    """
    for host in hosts:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return True
    return False


def _basename(command: str) -> str:
    """Komut satırının çalıştırılabilir adı (`/bin/bash -c ...` → `bash`)."""
    parts = command.split()
    if not parts:
        return ""
    return parts[0].lstrip("-").rsplit("/", maxsplit=1)[-1]


def parse_ps_parents(text: str) -> dict[int, int]:
    """`ps -eo pid=,ppid=` çıktısı → {pid: ppid}."""
    parents: dict[int, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            parents[int(fields[0])] = int(fields[1])
    return parents


def ancestor_pids(pid: int, parents: dict[int, int]) -> set[int]:
    """Sürecin kendisi ve tüm ataları. Kendi terminalimizi/`make`imizi öldürmemek için gerekir."""
    chain = {pid}
    current = pid
    while current in parents:
        current = parents[current]
        if current <= 0 or current in chain:
            break
        chain.add(current)
    return chain


def own_process_chain(pid: int, *, ps_text: str | None = None) -> set[int]:
    """Bu sürecin ata zinciri (pid'ler)."""
    text = ps_text if ps_text is not None else _run_ps_parents()
    return ancestor_pids(pid, parse_ps_parents(text))


def _run_ps_parents() -> str:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def parse_lsof_pids(text: str) -> list[int]:
    """`lsof -ti` çıktısını (satır başına bir pid) ayrıştırır."""
    pids: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.isdigit() and int(stripped) not in pids:
            pids.append(int(stripped))
    return pids


def port_listener_pids(port: int) -> list[int]:
    """Portu dinleyen süreçlerin pid'leri. `lsof` yoksa boş liste döner (tespit yapılamaz)."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=LSOF_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_lsof_pids(result.stdout)


def describe_pids(pids: list[int], *, ps_text: str | None = None) -> list[RunningProcess]:
    """Verilen pid'lerin komut satırlarını bulur; bulunamayanlar listeye girmez."""
    text = ps_text if ps_text is not None else _run_ps()
    wanted = set(pids)
    return [process for process in parse_ps_output(text) if process.pid in wanted]


def _run_ps() -> str:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=PS_TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout
