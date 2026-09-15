"""`make dev`: api + engine + arayüzü **birbirinden bağımsız** çalıştırır.

Kurallar (kullanıcı gereksinimi):
- Bir süreç çökerse diğerleri ayakta kalır. Çöken süreç kendiliğinden yeniden başlar.
- Toplu/sessiz ölüm yok: her çöküş ekrana açıkça yazılır, arayüzde de "engine kopuk" görünür.
- Başlarken bu depoya ait eski süreçler varsa temizlenir (yanlış ekrana bakma riskine karşı).
- Ortam senkronu **başlamadan önce bir kez** yapılır (Makefile); süreçler doğrudan venv python'u
  kullanır, böylece eşzamanlı `uv run` senkronu ve ondan doğan yarış durumu ortadan kalkar.
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

from marketpulse.core.version import git_sha
from marketpulse.devtools.procs import (
    HEALTHY_RUN_SEC,
    RunningProcess,
    backoff_delay,
    find_own_processes,
    port_is_busy,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"
API_PORT = 8000
WEB_PORT = 3000
POLL_SEC = 0.4
STOP_GRACE_SEC = 8.0


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    command: list[str]


@dataclass
class ManagedProcess:
    spec: ProcessSpec
    popen: subprocess.Popen[str] | None = None
    restarts: int = 0
    started_at: float = 0.0
    restart_at: float = 0.0
    reader: threading.Thread | None = None
    stopped: bool = False


def build_specs() -> list[ProcessSpec]:
    return [
        ProcessSpec(
            "api",
            [
                str(VENV_PYTHON),
                "-m",
                "uvicorn",
                "marketpulse.api.app:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                str(API_PORT),
                "--reload",
                "--reload-dir",
                "backend/src",
            ],
        ),
        ProcessSpec("engine", [str(VENV_PYTHON), "-m", "marketpulse.engine"]),
        ProcessSpec("web", ["npm", "--prefix", "frontend", "run", "dev"]),
    ]


class Supervisor:
    """Süreçleri başlatır, çıktılarını etiketler, çökenleri backoff ile yeniden başlatır."""

    def __init__(self, specs: list[ProcessSpec], *, write: Callable[[str], None] | None = None):
        self._managed = [ManagedProcess(spec=spec) for spec in specs]
        self._write = write or self._default_write
        self._print_lock = threading.Lock()
        self._stop = threading.Event()
        self._env = {**os.environ, "MP_GIT_SHA": git_sha(), "PYTHONUNBUFFERED": "1"}

    def run(self) -> int:
        for managed in self._managed:
            self._start(managed)
        self._install_signal_handlers()
        try:
            while not self._stop.is_set():
                self._tick()
                time.sleep(POLL_SEC)
        finally:
            self._shutdown()
        return 0

    def request_stop(self) -> None:
        self._stop.set()

    def _tick(self) -> None:
        now = time.monotonic()
        for managed in self._managed:
            if managed.popen is None:
                if managed.restart_at and now >= managed.restart_at:
                    self._start(managed)
                continue
            code = managed.popen.poll()
            if code is None:
                continue
            ran_for = now - managed.started_at
            if ran_for >= HEALTHY_RUN_SEC:
                managed.restarts = 0  # sağlıklı çalıştı: sayaç sıfırlanır
            managed.restarts += 1
            delay = backoff_delay(managed.restarts)
            managed.popen = None
            managed.restart_at = now + delay
            self._log(
                managed.spec.name,
                f"süreç durdu (çıkış kodu {code}). {delay:.0f} sn sonra yeniden başlıyor "
                f"({managed.restarts}. deneme). Diğer süreçler çalışmaya devam ediyor.",
            )

    def _start(self, managed: ManagedProcess) -> None:
        try:
            popen = subprocess.Popen(
                managed.spec.command,
                cwd=REPO_ROOT,
                env=self._env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            managed.restarts += 1
            managed.restart_at = time.monotonic() + backoff_delay(managed.restarts)
            self._log(managed.spec.name, f"başlatılamadı: {exc}")
            return
        managed.popen = popen
        managed.started_at = time.monotonic()
        managed.restart_at = 0.0
        reader = threading.Thread(target=self._pump, args=(managed.spec.name, popen), daemon=True)
        reader.start()
        managed.reader = reader
        self._log(managed.spec.name, f"başladı (pid {popen.pid})")

    def _pump(self, name: str, popen: subprocess.Popen[str]) -> None:
        stream = popen.stdout
        if stream is None:
            return
        for line in stream:
            self._log(name, line.rstrip("\n"))

    def _shutdown(self) -> None:
        self._log("dev", "kapatılıyor: tüm süreçlere durma sinyali gönderiliyor")
        for managed in self._managed:
            if managed.popen is not None:
                managed.popen.terminate()
        deadline = time.monotonic() + STOP_GRACE_SEC
        for managed in self._managed:
            if managed.popen is None:
                continue
            remaining = max(0.1, deadline - time.monotonic())
            try:
                managed.popen.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                managed.popen.kill()
        self._log("dev", "kapandı")

    def _install_signal_handlers(self) -> None:
        """Ctrl+C ve SIGTERM ile düzgün kapanış.

        Ana iş parçacığında değilsek (testte) sessizce atlanır.
        """

        def handler(_signum: int, _frame: FrameType | None) -> None:
            self.request_stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except ValueError:
                return

    def _log(self, name: str, message: str) -> None:
        with self._print_lock:
            self._write(f"{name:<6} | {message}")

    @staticmethod
    def _default_write(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def stop_stale_processes(*, clean: bool = True) -> list[RunningProcess]:
    """Bu depoya ait eski süreçleri bulur; `clean` ise durdurur. Bulunanları döner."""
    own_pids = {os.getpid(), os.getppid()}
    stale = find_own_processes(str(REPO_ROOT), exclude_pids=own_pids)
    if not stale:
        return []
    for process in stale:
        print(f"dev    | eski süreç bulundu: pid {process.pid} — {process.command[:90]}")
    if not clean:
        print("dev    | --no-clean verildi: süreçler durdurulmadı, karışıklık riski sürüyor")
        return stale
    for process in stale:
        _terminate(process.pid)
    time.sleep(1.0)
    for process in stale:
        _terminate(process.pid, force=True)
    print(f"dev    | {len(stale)} eski süreç durduruldu")
    return stale


def _terminate(pid: int, *, force: bool = False) -> None:
    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return


def check_ports() -> list[int]:
    """Hâlâ dolu olan portlar. Boş liste = yol açık."""
    return [port for port in (API_PORT, WEB_PORT) if port_is_busy(port)]


def preflight(*, clean: bool = True) -> bool:
    """Başlamadan önceki denetimler. False dönerse başlatma yapılmaz."""
    if not (REPO_ROOT / ".env").is_file():
        print("dev    | HATA: .env yok. Once sunu calistirin: cp .env.example .env")
        return False
    if not VENV_PYTHON.exists():
        print(f"dev    | HATA: backend ortamı yok ({VENV_PYTHON}). Once: make install")
        return False
    stop_stale_processes(clean=clean)
    busy = check_ports()
    if busy:
        ports = ", ".join(str(port) for port in busy)
        print(
            f"dev    | HATA: {ports} portu bize ait olmayan bir program tarafından kullanılıyor.\n"
            f"dev    | O programı kapatın ya da `lsof -i :{busy[0]}` ile kimin tuttuğuna bakın."
        )
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="marketpulse-dev",
        description="api + engine + arayüzü bağımsız süreçler olarak çalıştırır",
    )
    parser.add_argument(
        "--no-clean", action="store_true", help="eski süreçleri durdurma, yalnızca uyar"
    )
    parser.add_argument(
        "--stop", action="store_true", help="çalışan geliştirme yığınını durdur ve çık"
    )
    args = parser.parse_args()

    if args.stop:
        stopped = stop_stale_processes(clean=True)
        if not stopped:
            print("dev    | çalışan süreç bulunamadı")
        return 0

    if not preflight(clean=not args.no_clean):
        return 1
    print(f"dev    | commit {git_sha()} · arayüz http://localhost:{WEB_PORT}")
    return Supervisor(build_specs()).run()


if __name__ == "__main__":
    sys.exit(main())
