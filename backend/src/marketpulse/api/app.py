"""FastAPI uygulaması. Çalıştırma: `uvicorn marketpulse.api.app:create_app --factory`.

Api süreci DB'yi okur, outbox'ı WS istemcilerine yayınlar; yalnızca ayar/onay tablolarına yazar
(ARCHITECTURE.md §2). Migration'ları açılışta bu süreç koşar; engine şemayı bekler.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from marketpulse import __version__
from marketpulse.api.live_relay import LiveRelay, LiveState
from marketpulse.api.outbox_relay import RelayState, run_outbox_relay
from marketpulse.api.routers.calibration import router as calibration_router
from marketpulse.api.routers.health import router as health_router
from marketpulse.api.routers.market import router as market_router
from marketpulse.api.routers.predictions import router as predictions_router
from marketpulse.api.routers.signals import router as signals_router
from marketpulse.api.ws import WsHub, ws_endpoint
from marketpulse.collectors.ws_stream import ConnectFactory, binance_connect
from marketpulse.config import Settings, load_settings
from marketpulse.core.clock import Clock, SystemClock
from marketpulse.core.logging import configure_logging
from marketpulse.core.version import git_sha
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.migrate import run_migrations

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    migrate_on_start: bool = True,
    connect: ConnectFactory = binance_connect,
    live_prices: bool = True,
) -> FastAPI:
    """Uygulama fabrikası. Testler kendi `Settings` ve `FakeClock`'unu geçirir."""
    resolved_settings = settings or load_settings()
    resolved_clock = clock or SystemClock()
    if settings is None:
        configure_logging(resolved_settings.log_level, process="api")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if migrate_on_start:
            await asyncio.to_thread(run_migrations, resolved_settings.sync_db_url)
        engine = make_engine(resolved_settings.db_url)
        repo = SqliteRepository(engine, db_url=resolved_settings.db_url)
        hub = WsHub()
        relay_state = RelayState()
        stop = asyncio.Event()
        live_state = LiveState()
        tasks = [
            asyncio.create_task(
                run_outbox_relay(
                    repo,
                    hub,
                    resolved_clock,
                    relay_state,
                    stop,
                    poll_interval=resolved_settings.outbox_poll_interval_sec,
                ),
                name="outbox-relay",
            )
        ]
        if live_prices:
            relay = LiveRelay(
                resolved_settings.binance_ws_spot,
                list(resolved_settings.symbols),
                hub,
                resolved_clock,
                live_state,
                connect=connect,
            )
            tasks.append(asyncio.create_task(relay.run(stop), name="live-relay"))
        app.state.settings = resolved_settings
        app.state.clock = resolved_clock
        app.state.repo = repo
        app.state.hub = hub
        app.state.relay_state = relay_state
        app.state.live_state = live_state
        app.state.started_at = resolved_clock.now()
        logger.bind(process="api").info(
            "api başladı (sürüm {v}, commit {sha})", v=__version__, sha=git_sha()
        )
        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await repo.close()
            logger.bind(process="api").info("api kapandı")

    app = FastAPI(
        title="MarketPulse API",
        version=__version__,
        description="Yön olasılığı ve piyasa durumu. İşlem yapmaz.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(market_router, prefix=API_PREFIX)
    app.include_router(predictions_router, prefix=API_PREFIX)
    app.include_router(signals_router, prefix=API_PREFIX)
    app.include_router(calibration_router, prefix=API_PREFIX)
    app.add_api_websocket_route("/ws", ws_endpoint)
    return app
