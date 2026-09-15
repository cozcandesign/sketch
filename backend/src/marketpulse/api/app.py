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
from marketpulse.api.outbox_relay import RelayState, run_outbox_relay
from marketpulse.api.routers.health import router as health_router
from marketpulse.api.ws import WsHub, ws_endpoint
from marketpulse.config import Settings, load_settings
from marketpulse.core.clock import Clock, SystemClock
from marketpulse.core.logging import configure_logging
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.migrate import run_migrations

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    migrate_on_start: bool = True,
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
        relay_task = asyncio.create_task(
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
        app.state.settings = resolved_settings
        app.state.clock = resolved_clock
        app.state.repo = repo
        app.state.hub = hub
        app.state.relay_state = relay_state
        logger.bind(process="api").info("api başladı (sürüm {v})", v=__version__)
        try:
            yield
        finally:
            stop.set()
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task
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
    app.add_api_websocket_route("/ws", ws_endpoint)
    return app
