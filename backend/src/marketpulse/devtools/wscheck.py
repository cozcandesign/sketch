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
from dataclasses import dataclass
from typing import Any

from websockets.exceptions import WebSocketException

from marketpulse.collectors.orderflow_ws import streams_for
from marketpulse.collectors.ws_stream import binance_connect, combined_url
from marketpulse.config import Settings

DEFAULT_SECONDS = 30.0
PROGRESS_EVERY_SEC = 5.0
PROBE_SECONDS = 8.0
# Beklenen akış türleri: biri hiç gelmiyorsa abonelik ya da ad sorunudur.
EXPECTED_EVENTS = ("aggTrade", "forceOrder", "depthUpdate")


class _ClosedEarlyError(Exception):
    """Akış süre dolmadan bitti: sunucu kapattı demektir."""


@dataclass(frozen=True)
class Probe:
    """Tek bir deneme: etiket + bağlanılacak URL."""

    label: str
    url: str


@dataclass(frozen=True)
class ProbeResult:
    """Denemenin sonucu.

    `total` her tür mesajı sayar, `trades` yalnızca `aggTrade`'i. İkisi birlikte "bağlandık ama
    sessiz" ile "sunucu hiçbir şey göndermedi"yi ayırır. `ended` bağlantının nasıl bittiğini söyler:
    süre dolduysa akış açık kalmıştır, erken bittiyse karşı taraf kapatmıştır.
    """

    label: str
    total: int
    trades: int
    seconds: float
    ended: str

    @property
    def connected(self) -> bool:
        return not self.ended.startswith("bağlanamadı")

    def line(self) -> str:
        if not self.connected:
            return f"  {self.label:<32} → {self.ended}"
        return (
            f"  {self.label:<32} → {self.trades:>5} işlem | {self.total:>5} mesaj "
            f"| {self.seconds:>4.1f} sn | {self.ended}"
        )


def probe_plan(futures_base: str, spot_base: str, symbol: str) -> list[Probe]:
    """Dört deneme: işlem akışı (futures/spot) ve kontrol olarak çalıştığını bildiğimiz akış.

    Yazım hipotezi kullanıcının verisiyle elendi (üç yazım da sıfır). Şimdi ayırt edilecek soru:
    sorun futures işlem akışına mı özgü, yoksa bu ağda işlem akışlarının tamamı mı gelmiyor?
    Kontrol denemesi olmadan "hiçbir şey gelmedi" ölçümü yorumlanamaz.
    """
    lower = symbol.lower()
    futures_ws = futures_base.rstrip("/").removesuffix("/stream")
    spot_ws = spot_base.rstrip("/").removesuffix("/stream")
    return [
        Probe("futures işlem (/ws)", f"{futures_ws}/ws/{lower}@aggTrade"),
        Probe("futures derinlik (kontrol)", f"{futures_ws}/ws/{lower}@depth20@100ms"),
        Probe("spot işlem (/ws)", f"{spot_ws}/ws/{lower}@aggTrade"),
        Probe("spot mum (kontrol)", f"{spot_ws}/ws/{lower}@kline_1m"),
    ]


async def run_probe(probe: Probe, seconds: float) -> ProbeResult:
    """Tek denemeyi çalıştırır; mesaj sayar ve bağlantının nasıl bittiğini kaydeder."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    total = trades = 0
    ended = "süre doldu (akış açık kaldı)"

    async def pump() -> None:
        nonlocal total, trades
        async with binance_connect(probe.url) as messages:
            async for raw in messages:
                total += 1
                payload: Any = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                data = payload.get("data", payload)
                if isinstance(data, dict) and data.get("e") == "aggTrade":
                    trades += 1
        # Döngü kendiliğinden bitti: karşı taraf bağlantıyı kapattı.
        raise _ClosedEarlyError

    try:
        await asyncio.wait_for(pump(), timeout=seconds)
    except TimeoutError:
        pass
    except _ClosedEarlyError:
        ended = "sunucu kapattı"
    except (OSError, WebSocketException) as exc:
        ended = f"bağlanamadı: {type(exc).__name__}"
    return ProbeResult(probe.label, total, trades, loop.time() - started, ended)


async def probe_trade_streams(
    futures_base: str, spot_base: str, symbol: str, seconds: float
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for probe in probe_plan(futures_base, spot_base, symbol):
        result = await run_probe(probe, seconds)
        print(result.line(), flush=True)
        results.append(result)
    return results


def probe_verdict(results: list[ProbeResult]) -> str:
    """Ölçüme dayalı sonuç. Veri yetmiyorsa "bilmiyorum" der; tahmin üretmez."""
    by_label = {result.label: result for result in results}
    futures_trade = by_label.get("futures işlem (/ws)")
    futures_control = by_label.get("futures derinlik (kontrol)")
    spot_trade = by_label.get("spot işlem (/ws)")
    if futures_trade is None or futures_control is None or spot_trade is None:
        return "Deneme eksik: sonuç çıkarılamadı."

    if futures_trade.trades > 0:
        return "Futures işlem akışı bu denemede veri verdi: sorun engine'in abonelik kurulumunda."
    if not futures_control.connected or futures_control.total == 0:
        return (
            "Kontrol denemesi de veri vermedi: ölçüm güvenilir değil (ağ ya da bağlantı sorunu). "
            "Önce bunu çözmek gerekir."
        )
    if spot_trade.trades > 0:
        return (
            "Spot işlem akışı çalışıyor, futures işlem akışı çalışmıyor. Sorun bu ağdan "
            "futures işlem akışına özgü; derinlik akışı geldiği için bağlantının kendisi sağlam."
        )
    return (
        "Ne futures ne spot işlem akışı veri verdi; derinlik ve mum akışları geliyor. "
        "İşlem akışları bu ağda engelleniyor olabilir."
    )


def progress_line(elapsed: float, events: Counter[str]) -> str:
    """Ara durum satırı: beklenen üç olayın o ana kadarki sayısı.

    Araç 30 saniye sessiz durursa donmuş sanılıyor; dahası kullanıcı yarıda kesse bile bu
    satırlar sorunun cevabını zaten veriyor (CLAUDE.md §2).
    """
    counts = " ".join(f"{event} {events[event]}" for event in EXPECTED_EVENTS)
    return f"  {elapsed:>3.0f} sn | toplam {sum(events.values()):>6} | {counts}"


async def listen(
    url: str, seconds: float, *, progress_every: float = PROGRESS_EVERY_SEC
) -> tuple[Counter[str], Counter[str], str | None]:
    """`seconds` boyunca dinler. (akış adı sayaçları, olay türü sayaçları, ilk işlem örneği)."""
    streams: Counter[str] = Counter()
    events: Counter[str] = Counter()
    first_trade: str | None = None

    async def ticker() -> None:
        elapsed = 0.0
        while True:
            await asyncio.sleep(progress_every)
            elapsed += progress_every
            print(progress_line(elapsed, events), flush=True)

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

    progress = asyncio.create_task(ticker())
    try:
        # Süre dolunca dinleme biter; bu normal bitiştir, hata değil.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(pump(), timeout=seconds)
    finally:
        progress.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await progress
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
    print("Dinleniyor; her 5 saniyede bir ara durum yazılır.\n")

    try:
        streams, events, first_trade = await listen(url, args.seconds)
    except (OSError, WebSocketException) as exc:
        # Kullanıcı yazılımcı değil: yığın izi yerine ne olduğunu söyle (CLAUDE.md §2).
        print(f"\nBağlanılamadı: {exc}")
        print("Olası sebepler: internet yok, Binance bu ağdan engelli (ABD IP'leri engellenir),")
        print("ya da .env içindeki MP_BINANCE_WS_FUTURES adresi yanlış.")
        return 1
    report(streams, events, first_trade)

    if events["aggTrade"] == 0:
        print(f"\nİşlem akışı gelmedi. Dört deneme yapılıyor ({PROBE_SECONDS:.0f} sn × 4):")
        results = await probe_trade_streams(
            settings.binance_ws_futures, settings.binance_ws_spot, symbols[0], PROBE_SECONDS
        )
        print(f"\n{probe_verdict(results)}")
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
