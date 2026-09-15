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
    içeriyorsa sayılır; başka bir projenin Vite sunucusu asla dokunulmaz.
    """
    if any(pattern in command for pattern in OWN_PROCESS_PATTERNS):
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


def port_is_busy(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Port dinleniyor mu? (Bağlanabiliyorsak doludur.)"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


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
