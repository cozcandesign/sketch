"""Engine süreci: `python -m marketpulse.engine`.

Faz 0'da yalnızca heartbeat işi çalışır. Collector'lar ve tahmin işleri sonraki fazlarda buraya
supervisor altında eklenir (ARCHITECTURE.md §2, §5, §17).
"""

import asyncio
import signal
from datetime import timedelta

from loguru import logger

from marketpulse import __version__
from marketpulse.config import Settings, load_settings
from marketpulse.core.clock import Clock, SystemClock
from marketpulse.core.errors import EngineAlreadyRunningError
from marketpulse.core.logging import configure_logging
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.jobs import make_heartbeat, run_every
from marketpulse.engine.supervisor import supervise
from marketpulse.storage import Outbox, Repository, SqliteRepository, make_engine
from marketpulse.storage.migrate import run_migrations, wait_for_schema

SHUTDOWN_GRACE_SEC = 10.0
SCHEMA_WAIT_SEC = 60.0


async def ensure_single_instance(repo: Repository, clock: Clock, stale_after_sec: float) -> None:
    """Taze heartbeat varsa ikinci örnek başlamaz (compose restart senaryosu)."""
    heartbeat = await repo.read_heartbeat()
    if heartbeat is None:
        return
    age = clock.now() - heartbeat.ts
    if age < timedelta(seconds=stale_after_sec):
        msg = (
            f"engine zaten çalışıyor görünüyor: son heartbeat {heartbeat.ts.isoformat()} "
            f"({age.total_seconds():.0f} sn önce, eşik {stale_after_sec:.0f} sn). "
            "Diğer örnek kapanana ya da heartbeat bayatlayana kadar bekleyin."
        )
        raise EngineAlreadyRunningError(msg)


async def run(
    settings: Settings,
    *,
    clock: Clock | None = None,
    stop: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
    schema_wait_sec: float = SCHEMA_WAIT_SEC,
) -> None:
    """Engine ana döngüsü. `stop` set edilince görevler kapatılır, heartbeat temizlenir."""
    clock = clock or SystemClock()
    stop = stop or asyncio.Event()
    log = logger.bind(process="engine")

    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    try:
        if not await wait_for_schema(engine, timeout_sec=schema_wait_sec):
            log.warning(
                "şema {t:.0f} sn içinde hazır olmadı; migration engine tarafından koşuluyor",
                t=schema_wait_sec,
            )
            await asyncio.to_thread(run_migrations, settings.sync_db_url)
        await ensure_single_instance(repo, clock, settings.heartbeat_stale_after_sec)

        if install_signal_handlers:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stop.set)

        health = HealthRegistry(clock)
        outbox = Outbox(repo, clock)
        heartbeat = make_heartbeat(repo, health, outbox, clock, __version__)
        tasks = [
            asyncio.create_task(
                supervise(
                    "heartbeat",
                    lambda: run_every(
                        "heartbeat", settings.heartbeat_interval_sec, heartbeat, stop
                    ),
                    stop,
                    health,
                ),
                name="heartbeat",
            ),
        ]
        log.info("engine başladı (sürüm {v}, semboller {s})", v=__version__, s=settings.symbols)
        await stop.wait()
        log.info("kapanış sinyali alındı; görevler kapatılıyor")
        for task in tasks:
            task.cancel()
        await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SEC)
        await repo.clear_heartbeat()
    finally:
        await repo.close()
    log.info("engine kapandı")


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level, process="engine")
    asyncio.run(run(settings))
