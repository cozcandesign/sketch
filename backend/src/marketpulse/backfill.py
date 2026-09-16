"""Geçmiş veri çekme komutu: `make backfill` (ROADMAP F1-13).

Kapsam: spot mumlar + türev geçmişi (funding, açık pozisyon, long/short, taker hacmi).
Fear & Greed ve makro serileri kendi fazlarında eklenir.

Komut idempotenttir: tekrar çalıştırmak veriyi bozmaz, eksikleri tamamlar. Türev verisi Binance'te
yalnızca son 30 gün tutulur (funding hariç); biz sildirmeyiz, arşiv ilk günden birikir (K5, K21).
"""

import argparse
import asyncio
from datetime import timedelta

from loguru import logger

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.binance_futures import FuturesClient
from marketpulse.collectors.futures import (
    FundingCollector,
    LongShortCollector,
    OpenInterestCollector,
    TakerVolumeCollector,
)
from marketpulse.collectors.klines import BACKFILL_LOOKBACK, KlinesCollector
from marketpulse.config import Settings, load_settings
from marketpulse.core.clock import SystemClock
from marketpulse.core.logging import configure_logging
from marketpulse.core.types import Interval, parse_symbol
from marketpulse.engine.main import CANDLE_INTERVALS
from marketpulse.engine.ratelimit import RateLimiter
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.migrate import run_migrations

DEFAULT_INTERVALS_TEXT = ",".join(i.value for i in CANDLE_INTERVALS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketpulse-backfill", description="Geçmiş mum verisini Binance'ten çeker."
    )
    parser.add_argument(
        "--symbols", help="Virgülle ayrılmış sembol listesi (varsayılan: .env içindekiler)"
    )
    parser.add_argument(
        "--intervals",
        help=f"Virgülle ayrılmış zaman dilimleri (varsayılan: {DEFAULT_INTERVALS_TEXT})",
    )
    parser.add_argument(
        "--days", type=int, help="Tüm zaman dilimleri için gün sayısını geçersiz kılar"
    )
    parser.add_argument(
        "--skip-derivatives",
        action="store_true",
        help="Yalnızca mumları çeker; funding/OI/long-short/taker atlanır",
    )
    return parser


async def run_backfill(
    symbols: list[str] | None = None,
    intervals: list[Interval] | None = None,
    days: int | None = None,
    *,
    derivatives: bool = True,
) -> int:
    settings = load_settings()
    configure_logging(settings.log_level, process="backfill")
    await asyncio.to_thread(run_migrations, settings.sync_db_url)

    clock = SystemClock()
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    limiter = RateLimiter(clock, name="binance_spot")
    client = BinanceClient(settings.binance_spot_base, limiter)
    chosen_symbols = symbols or list(settings.symbols)
    chosen_intervals = intervals or list(CANDLE_INTERVALS)
    lookback = (
        {i: timedelta(days=days) for i in chosen_intervals} if days else dict(BACKFILL_LOOKBACK)
    )
    try:
        weight_limit = await client.weight_limit()
        if weight_limit is not None:
            limiter.apply_limit(weight_limit)
        collector = KlinesCollector(
            client, repo, clock, symbols=chosen_symbols, intervals=chosen_intervals
        )
        logger.info(
            "geçmiş doldurma başlıyor: {s} × {i}",
            s=",".join(chosen_symbols),
            i=",".join(i.value for i in chosen_intervals),
        )
        written = await collector.backfill(lookback=lookback)
        if derivatives:
            await _backfill_derivatives(settings, repo, clock, chosen_symbols)
        for symbol in chosen_symbols:
            counts = {
                interval.value: await repo.count_candles(symbol, interval)
                for interval in chosen_intervals
            }
            logger.bind(symbol=symbol).info("mum sayıları: {c}", c=counts)
    finally:
        await client.aclose()
        await repo.close()
    return written


async def _backfill_derivatives(
    settings: Settings, repo: SqliteRepository, clock: SystemClock, symbols: list[str]
) -> None:
    """Türev geçmişi. Bir uç nokta başarısız olursa diğerleri yine denenir; mumlar etkilenmez."""
    limiter = RateLimiter(clock, name="binance_futures")
    client = BinanceClient(settings.binance_futures_base, limiter)
    futures = FuturesClient(client)
    try:
        tasks = (
            ("funding", FundingCollector(futures, repo, clock, symbols=symbols).backfill),
            (
                "open_interest",
                OpenInterestCollector(futures, repo, clock, symbols=symbols).backfill,
            ),
            ("long_short", LongShortCollector(futures, repo, symbols=symbols).poll),
            ("taker_volume", TakerVolumeCollector(futures, repo, symbols=symbols).poll),
        )
        for name, task in tasks:
            try:
                count = await task()
                logger.bind(collector=name).info("türev geçmişi: {n} satır", n=count)
            except Exception as exc:  # bir veri seti eksik kalabilir, komut çökmez
                logger.bind(collector=name).warning("türev geçmişi alınamadı: {e}", e=repr(exc))
    finally:
        await client.aclose()


def main() -> None:
    args = build_parser().parse_args()
    symbols = [parse_symbol(s) for s in args.symbols.split(",")] if args.symbols else None
    intervals = [Interval(i.strip()) for i in args.intervals.split(",")] if args.intervals else None
    written = asyncio.run(
        run_backfill(symbols, intervals, args.days, derivatives=not args.skip_derivatives)
    )
    logger.info("bitti: {n} mum yazıldı", n=written)


if __name__ == "__main__":
    main()
