"""Binance combined WebSocket akışı için ince sarmalayıcı.

Testler gerçek bağlantı yerine sahte bir `ConnectFactory` geçirir; böylece testte ağ olmaz
(CLAUDE.md §8).
"""

import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager

from websockets.asyncio.client import connect as ws_connect

PING_INTERVAL_SEC = 20
PING_TIMEOUT_SEC = 20
MAX_STREAMS_PER_CONNECTION = 200

ConnectFactory = Callable[[str], AbstractAsyncContextManager[AsyncIterator[str]]]


def combined_url(base_url: str, streams: list[str]) -> str:
    """`wss://.../stream` + `?streams=a/b/c`. Boş liste geçersizdir."""
    if not streams:
        msg = "en az bir stream gerekir"
        raise ValueError(msg)
    if len(streams) > MAX_STREAMS_PER_CONNECTION:
        msg = f"tek bağlantıda en fazla {MAX_STREAMS_PER_CONNECTION} stream olabilir"
        raise ValueError(msg)
    return f"{base_url.rstrip('/')}?streams={'/'.join(streams)}"


@contextlib.asynccontextmanager
async def binance_connect(url: str) -> AsyncIterator[AsyncIterator[str]]:
    """Gerçek Binance bağlantısı. Mesajları metin olarak veren bir akış döndürür."""
    async with ws_connect(
        url, ping_interval=PING_INTERVAL_SEC, ping_timeout=PING_TIMEOUT_SEC
    ) as socket:

        async def messages() -> AsyncIterator[str]:
            async for raw in socket:
                yield raw if isinstance(raw, str) else raw.decode()

        yield messages()
