"""Engine süreci: `python -m marketpulse.engine` (ARCHITECTURE.md §2, §5, §17).

Çalışanlar: mum toplayıcıları (REST geçmiş + boşluk, WS canlı), canlı tahmin (sinyal modülleri →
ensemble → rapor), referans tahminciler, sonuç çözümleyici, saklama ve heartbeat.
"""

import asyncio
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from loguru import logger

from marketpulse import __version__
from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.binance_futures import FuturesClient
from marketpulse.collectors.futures import (
    FundingCollector,
    LongShortCollector,
    OpenInterestCollector,
    TakerVolumeCollector,
)
from marketpulse.collectors.klines import KlinesCollector
from marketpulse.collectors.klines_ws import KlinesWsCollector
from marketpulse.collectors.orderflow_ws import OrderflowWsCollector
from marketpulse.collectors.ws_stream import ConnectFactory, binance_connect
from marketpulse.config import Settings, load_settings
from marketpulse.core.clock import Clock, SystemClock
from marketpulse.core.errors import EngineAlreadyRunningError
from marketpulse.core.logging import configure_logging
from marketpulse.core.time import floor_to_minute
from marketpulse.core.types import Horizon, Interval
from marketpulse.core.version import git_sha
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.jobs import Job, JobFn, run_jobs
from marketpulse.engine.predict import LivePredictor, run_baseline_predictions
from marketpulse.engine.ratelimit import RateLimiter
from marketpulse.engine.retention import run_retention
from marketpulse.engine.supervisor import supervise
from marketpulse.ensemble.weights import load_default_weights
from marketpulse.features.feature_store import FeatureStore
from marketpulse.storage import Outbox, Repository, SqliteRepository, make_engine
from marketpulse.storage.migrate import run_migrations, wait_for_schema
from marketpulse.tracking.ledger import Ledger
from marketpulse.tracking.resolver import Resolver

SHUTDOWN_GRACE_SEC = 10.0
SCHEMA_WAIT_SEC = 60.0
PREDICT_OFFSET = timedelta(seconds=10)  # tetik dakikasının mumu kapansın diye
CANDLE_INTERVALS: tuple[Interval, ...] = (
    Interval.M1,
    Interval.M5,
    Interval.M15,
    Interval.H1,
    Interval.H4,
    Interval.D1,
)


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


@dataclass(frozen=True)
class DerivativeCollectors:
    """Türev REST toplayıcıları; engine ve testler aynı demeti kullanır."""

    funding: FundingCollector
    open_interest: OpenInterestCollector
    long_short: LongShortCollector
    taker_volume: TakerVolumeCollector

    @property
    def names(self) -> tuple[str, ...]:
        return (
            self.funding.name,
            self.open_interest.name,
            self.long_short.name,
            self.taker_volume.name,
        )


def build_derivative_collectors(
    client: BinanceClient, repo: Repository, clock: Clock, symbols: list[str]
) -> DerivativeCollectors:
    futures = FuturesClient(client)
    return DerivativeCollectors(
        funding=FundingCollector(futures, repo, clock, symbols=symbols),
        open_interest=OpenInterestCollector(futures, repo, clock, symbols=symbols),
        long_short=LongShortCollector(futures, repo, symbols=symbols),
        taker_volume=TakerVolumeCollector(futures, repo, symbols=symbols),
    )


def build_jobs(
    *,
    repo: Repository,
    ledger: Ledger,
    predictor: LivePredictor,
    resolver: Resolver,
    klines: KlinesCollector,
    derivatives: DerivativeCollectors,
    health: HealthRegistry,
    outbox: Outbox,
    clock: Clock,
    symbols: list[str],
    heartbeat_interval_sec: float,
) -> list[Job]:
    """ARCHITECTURE.md §5'teki iş tablosu."""

    async def heartbeat(_scheduled: datetime) -> None:
        await repo.write_heartbeat(clock.now(), __version__)
        await health.flush(repo, outbox)

    def predict_job(horizon: Horizon) -> Callable[[datetime], Awaitable[None]]:
        async def run(scheduled: datetime) -> None:
            as_of = floor_to_minute(scheduled)
            live = await predictor.run(symbols=symbols, horizon=horizon, as_of=as_of)
            baseline = await run_baseline_predictions(
                repo, ledger, symbols=symbols, horizon=horizon, as_of=as_of
            )
            logger.bind(job=f"predict_{horizon.value}", horizon=horizon.value).info(
                "{live} canlı + {base} referans tahmin yazıldı (as_of {at})",
                live=live,
                base=baseline,
                at=as_of.isoformat(),
            )

        return run

    async def resolve(_scheduled: datetime) -> None:
        stats = await resolver.resolve_due()
        if stats.resolved or stats.unresolved:
            logger.bind(job="resolve").info(
                "çözümlendi: {r}, çözümlenemedi: {u}, bekleyen: {w}",
                r=stats.resolved,
                u=stats.unresolved,
                w=stats.waiting,
            )

    async def gap_check(_scheduled: datetime) -> None:
        await klines.fill_gaps()

    def collector_job(name: str, work: Callable[[], Awaitable[int]]) -> JobFn:
        """Collector işini sağlık kaydına bağlar: hata engine'i düşürmez (CLAUDE.md §6)."""

        async def run(_scheduled: datetime) -> None:
            try:
                written = await work()
            except Exception as exc:
                health.record_error(name, exc)
                logger.bind(collector=name).warning("toplama başarısız: {e}", e=repr(exc))
                return
            health.record_success(name)
            logger.bind(collector=name).debug("{n} satır yazıldı", n=written)

        return run

    async def retention(_scheduled: datetime) -> None:
        await run_retention(repo, clock)

    return [
        Job("heartbeat", timedelta(seconds=heartbeat_interval_sec), heartbeat),
        Job("resolve", timedelta(minutes=1), resolve, offset=timedelta(seconds=30)),
        Job("gap_check", timedelta(minutes=5), gap_check, offset=timedelta(seconds=20)),
        Job("retention", timedelta(days=1), retention, offset=timedelta(hours=3)),
        *[
            Job(f"predict_{h.value}", h.cadence, predict_job(h), offset=PREDICT_OFFSET)
            for h in Horizon
        ],
        # Türev metrikleri: anlık okumalar dakikalık, 5 dk ızgarasındaki seriler 5 dakikalık,
        # geçmiş tamamlamaları seyrek (ARCHITECTURE.md §4 sıklık sütunu).
        Job(
            "funding_live",
            timedelta(minutes=1),
            collector_job(derivatives.funding.name, derivatives.funding.poll_live),
            offset=timedelta(seconds=5),
        ),
        Job(
            "open_interest_live",
            timedelta(minutes=1),
            collector_job(derivatives.open_interest.name, derivatives.open_interest.poll_live),
            offset=timedelta(seconds=8),
        ),
        Job(
            "long_short",
            timedelta(minutes=5),
            collector_job(derivatives.long_short.name, derivatives.long_short.poll),
            offset=timedelta(seconds=40),
        ),
        Job(
            "taker_volume",
            timedelta(minutes=5),
            collector_job(derivatives.taker_volume.name, derivatives.taker_volume.poll),
            offset=timedelta(seconds=50),
        ),
        Job(
            "open_interest_hist",
            timedelta(hours=1),
            collector_job(derivatives.open_interest.name, derivatives.open_interest.backfill),
            offset=timedelta(minutes=2),
        ),
        Job(
            "funding_hist",
            timedelta(hours=8),
            collector_job(derivatives.funding.name, derivatives.funding.backfill),
            offset=timedelta(minutes=4),
        ),
    ]


async def _startup_tasks(
    client: BinanceClient, limiter: RateLimiter, klines: KlinesCollector, health: HealthRegistry
) -> None:
    """Gerçek ağırlık limitini uygular ve geçmişi doldurur. Hata engine'i düşürmez."""
    try:
        weight_limit = await client.weight_limit()
        if weight_limit is not None:
            limiter.apply_limit(weight_limit)
        await klines.backfill()
        health.record_success(klines.name)
    except Exception as exc:
        health.record_error(klines.name, exc)
        logger.bind(collector=klines.name).warning("açılış görevleri başarısız: {e}", e=repr(exc))


@dataclass(frozen=True)
class EngineRuntime:
    """Engine'in çalışma parçaları. `run()` okunur kalsın diye ayrı kurulur."""

    health: HealthRegistry
    klines: KlinesCollector
    klines_ws: KlinesWsCollector
    orderflow_ws: OrderflowWsCollector
    jobs: list[Job]


async def build_runtime(
    settings: Settings,
    repo: SqliteRepository,
    clock: Clock,
    *,
    connect: ConnectFactory,
    client: BinanceClient,
    futures_client: BinanceClient,
) -> EngineRuntime:
    """Collector'ları, tahmin yolunu ve iş listesini kurar; sağlık kayıtlarını açar."""
    health = HealthRegistry(clock)
    outbox = Outbox(repo, clock)
    symbols = list(settings.symbols)
    klines = KlinesCollector(client, repo, clock, symbols=symbols, intervals=CANDLE_INTERVALS)
    klines_ws = KlinesWsCollector(
        settings.binance_ws_spot, repo, clock, health, symbols=symbols, connect=connect
    )
    orderflow_ws = OrderflowWsCollector(
        settings.binance_ws_futures, repo, clock, health, symbols=symbols, connect=connect
    )
    derivatives = build_derivative_collectors(futures_client, repo, clock, symbols)
    for name in (klines.name, klines_ws.name, orderflow_ws.name, *derivatives.names):
        health.register(name)

    ledger = Ledger(repo, clock, outbox)
    resolver = Resolver(repo, clock, outbox, backfill=klines)
    # Ağırlıklar yalnızca tablo boşken tohumlanır; K3 gereği üzerine yazılmaz.
    seeded = await repo.seed_weights(load_default_weights(), valid_from=clock.now())
    if seeded:
        logger.bind(process="engine").info("varsayılan ağırlıklar tohumlandı ({n} satır)", n=seeded)
    predictor = LivePredictor(repo, ledger, FeatureStore(repo), outbox=outbox)
    jobs = build_jobs(
        repo=repo,
        ledger=ledger,
        predictor=predictor,
        resolver=resolver,
        klines=klines,
        derivatives=derivatives,
        health=health,
        outbox=outbox,
        clock=clock,
        symbols=symbols,
        heartbeat_interval_sec=settings.heartbeat_interval_sec,
    )
    for job in jobs:
        health.register(job.name, expected_interval=job.every)
    return EngineRuntime(
        health=health, klines=klines, klines_ws=klines_ws, orderflow_ws=orderflow_ws, jobs=jobs
    )


async def run(
    settings: Settings,
    *,
    clock: Clock | None = None,
    stop: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
    schema_wait_sec: float = SCHEMA_WAIT_SEC,
    connect: ConnectFactory = binance_connect,
    http: httpx.AsyncClient | None = None,
    run_startup_tasks: bool = True,
) -> None:
    """Engine ana döngüsü. `stop` set edilince görevler kapatılır, heartbeat temizlenir."""
    clock = clock or SystemClock()
    stop = stop or asyncio.Event()
    log = logger.bind(process="engine")

    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    limiter = RateLimiter(clock, name="binance_spot")
    client = BinanceClient(settings.binance_spot_base, limiter, http=http)
    futures_limiter = RateLimiter(clock, name="binance_futures")
    futures_client = BinanceClient(settings.binance_futures_base, futures_limiter, http=http)
    try:
        if not await wait_for_schema(engine, timeout_sec=schema_wait_sec):
            log.warning("şema hazır değil; migration engine tarafından koşuluyor")
            await asyncio.to_thread(run_migrations, settings.sync_db_url)
        await ensure_single_instance(repo, clock, settings.heartbeat_stale_after_sec)

        if install_signal_handlers:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stop.set)

        parts = await build_runtime(
            settings, repo, clock, connect=connect, futures_client=futures_client, client=client
        )
        health, klines, klines_ws, orderflow_ws, jobs = (
            parts.health,
            parts.klines,
            parts.klines_ws,
            parts.orderflow_ws,
            parts.jobs,
        )

        tasks = [
            asyncio.create_task(
                supervise("jobs", lambda: run_jobs(jobs, stop, clock, health), stop, health),
                name="jobs",
            ),
            asyncio.create_task(
                supervise("klines_ws", lambda: klines_ws.run(stop), stop, health), name="klines_ws"
            ),
            asyncio.create_task(
                supervise("ws_orderflow", lambda: orderflow_ws.run(stop), stop, health),
                name="ws_orderflow",
            ),
        ]
        if run_startup_tasks:
            tasks.append(
                asyncio.create_task(_startup_tasks(client, limiter, klines, health), name="startup")
            )
        log.info(
            "engine başladı (sürüm {v}, commit {sha}, semboller {s})",
            v=__version__,
            sha=git_sha(),
            s=list(settings.symbols),
        )
        await stop.wait()
        log.info("kapanış sinyali alındı; görevler kapatılıyor")
        for task in tasks:
            task.cancel()
        await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SEC)
        await repo.clear_heartbeat()
    finally:
        await client.aclose()
        await futures_client.aclose()
        await repo.close()
    log.info("engine kapandı")


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level, process="engine")
    asyncio.run(run(settings))
