"""Futures WS teşhis aracı: hangi akıştan kaç mesaj geliyor? (geliştirme aracı)

Canlıda görülen belirti: order book verisi geliyor ama işlem (`aggTrade`) sayısı sıfır kalıyor.
Sebebi ancak Binance'e erişebilen bir makinede ölçülebilir. Bu araç engine'in **birebir aynı**
URL'sine bağlanır, sayar ve düz Türkçe özet basar. Veritabanına hiçbir şey yazmaz.

Kullanım: `make wscheck` (varsayılan 30 saniye) veya `make wscheck ARGS="--seconds 60"`.
"""

import argparse
import asyncio
import contextlib
import json
from collections import Counter
from typing import Any

from websockets.exceptions import WebSocketException

from marketpulse.collectors.orderflow_ws import streams_for
from marketpulse.collectors.ws_stream import binance_connect, combined_url
from marketpulse.config import Settings

DEFAULT_SECONDS = 30.0
# Beklenen akış türleri: biri hiç gelmiyorsa abonelik ya da ad sorunudur.
EXPECTED_EVENTS = ("aggTrade", "forceOrder", "depthUpdate")


async def listen(url: str, seconds: float) -> tuple[Counter[str], Counter[str], str | None]:
    """`seconds` boyunca dinler. (akış adı sayaçları, olay türü sayaçları, ilk işlem örneği)."""
    streams: Counter[str] = Counter()
    events: Counter[str] = Counter()
    first_trade: str | None = None

    async def pump() -> None:
        nonlocal first_trade
        async with binance_connect(url) as messages:
            async for raw in messages:
                payload: Any = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                streams[str(payload.get("stream", "(akış adı yok)"))] += 1
                data = payload.get("data", payload)
                event = str(data.get("e", "(olay adı yok)")) if isinstance(data, dict) else "?"
                events[event] += 1
                if event == "aggTrade" and first_trade is None:
                    first_trade = json.dumps(data, ensure_ascii=False)[:300]

    # Süre dolunca dinleme biter; bu normal bitiştir, hata değil.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(pump(), timeout=seconds)
    return streams, events, first_trade


def report(streams: Counter[str], events: Counter[str], first_trade: str | None) -> None:
    total = sum(events.values())
    print(f"\nToplam mesaj: {total}")
    if total == 0:
        print("Hiç mesaj gelmedi. Bağlantı kuruldu ama akış boş: URL ya da ağ engeli.")
        return

    print("\nOlay türüne göre:")
    for event, count in events.most_common():
        print(f"  {event:<14} {count}")
    for expected in EXPECTED_EVENTS:
        if events[expected] == 0:
            print(f"  ! {expected} hiç gelmedi")

    print("\nAkışa göre:")
    for stream, count in sorted(streams.items()):
        print(f"  {stream:<28} {count}")

    if first_trade:
        print(f"\nİlk işlem mesajı (kısaltıldı):\n  {first_trade}")
    else:
        print("\nİşlem mesajı hiç gelmedi: order flow modülünde CVD bileşeni bu yüzden boş kalır.")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Futures WS akışlarını dinler ve sayar")
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    parser.add_argument(
        "--symbol", action="append", default=None, help="varsayılan: .env sembolleri"
    )
    args = parser.parse_args(argv)

    settings = Settings()
    symbols = args.symbol or list(settings.symbols)
    url = combined_url(settings.binance_ws_futures, streams_for(symbols))
    print(f"Bağlanılıyor ({args.seconds:.0f} sn): {url}")

    try:
        streams, events, first_trade = await listen(url, args.seconds)
    except (OSError, WebSocketException) as exc:
        # Kullanıcı yazılımcı değil: yığın izi yerine ne olduğunu söyle (CLAUDE.md §2).
        print(f"\nBağlanılamadı: {exc}")
        print("Olası sebepler: internet yok, Binance bu ağdan engelli (ABD IP'leri engellenir),")
        print("ya da .env içindeki MP_BINANCE_WS_FUTURES adresi yanlış.")
        return 1
    report(streams, events, first_trade)
    return 0


def _quiet_transport_noise(loop: asyncio.AbstractEventLoop) -> None:
    """Bağlantı reddedilince websockets kütüphanesi arka planda yığın izi basıyor.

    Teşhis aracının çıktısı okunur kalsın: taşıma katmanı kapanış gürültüsü yutulur, gerçek
    hata zaten `main()` içinde düz cümleyle yazılır.
    """
    loop.set_exception_handler(lambda _loop, _context: None)


def run() -> int:
    async def _main() -> int:
        _quiet_transport_noise(asyncio.get_running_loop())
        return await main()

    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(run())
