"""Repository'nin döndürdüğü veri modelleri. DB satırları ↔ tipli nesneler."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from marketpulse.core.types import Horizon, Interval

HealthStatus = Literal["ok", "degraded", "down", "disabled", "budget_exhausted"]
PredictionSource = Literal["live", "baseline", "backtest"]
OutcomeLabel = Literal["up", "down", "unresolved"]
ConfidenceLabel = Literal["low", "mid", "high"]


class Heartbeat(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: datetime
    version: str


class CollectorHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    collector: str
    status: HealthStatus
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


class OutboxEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    created_at: datetime
    topic: str
    payload: dict[str, Any]


class Candle(BaseModel):
    """Kapanmış mum. `close_time = open_time + interval` (Binance'in -1 ms'i normalize edilir)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: Interval
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    trades: int = 0
    taker_buy_base: float = 0.0
    close_time: datetime

    @property
    def is_green(self) -> bool:
        return self.close > self.open


class CandleGap:
    """Mum serisinde eksik aralık: [start, end) — her ikisi de open_time."""

    __slots__ = ("end", "start")

    def __init__(self, start: datetime, end: datetime) -> None:
        self.start = start
        self.end = end

    def __repr__(self) -> str:
        return f"CandleGap({self.start.isoformat()}..{self.end.isoformat()})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CandleGap) and self.start == other.start and self.end == other.end

    def __hash__(self) -> int:
        return hash((self.start, self.end))


class NewPrediction(BaseModel):
    """Deftere yazılacak tahmin (ARCHITECTURE.md §6.3)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    horizon: Horizon
    as_of: datetime
    target_at: datetime
    price_at: float
    p_up: float
    expected_low: float | None = None
    expected_high: float | None = None
    confidence: float
    confidence_label: ConfidenceLabel
    conflict: bool = False
    veto_active: bool = False
    veto_reason: str | None = None
    combined_score: float | None = None
    weights: dict[str, float] | None = None
    ensemble_version: str
    non_overlapping: bool
    source: PredictionSource
    run_id: str | None = None
    report: dict[str, Any] | None = None


class SignalRow(BaseModel):
    """Tahmin anındaki tek modül skoru."""

    model_config = ConfigDict(frozen=True)

    module: str
    score: float
    confidence: float
    coverage: float
    components: dict[str, float] | None = None
    rationale: list[str] | None = None
    data_as_of: datetime | None = None


class PredictionOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    prediction_id: int
    resolved_at: datetime
    price_at_target: float | None
    realized_return: float | None
    outcome: OutcomeLabel
    hit: bool | None
    brier: float | None
    resolved_by: str


class Prediction(BaseModel):
    """Defterden okunan tahmin (varsa sonucuyla)."""

    model_config = ConfigDict(frozen=True)

    id: int
    created_at: datetime
    symbol: str
    horizon: Horizon
    as_of: datetime
    target_at: datetime
    price_at: float
    p_up: float
    expected_low: float | None
    expected_high: float | None
    confidence: float
    confidence_label: ConfidenceLabel
    conflict: bool
    veto_active: bool
    veto_reason: str | None
    combined_score: float | None
    weights: dict[str, float] | None
    ensemble_version: str
    non_overlapping: bool
    source: PredictionSource
    run_id: str | None
    report: dict[str, Any] | None
    outcome: PredictionOutcome | None = None
    signals: list[SignalRow] | None = None


class ModuleResolvedRow(BaseModel):
    """Bir modülün tek bir çözümlenmiş tahmindeki skoru ve gerçekleşen yön."""

    model_config = ConfigDict(frozen=True)

    module: str
    score: float
    coverage: float
    horizon: Horizon
    as_of: datetime
    non_overlapping: bool
    y: int  # 1 = yukarı, 0 = aşağı


class ResolvedRow(BaseModel):
    """Metrik hesabı için sadeleştirilmiş çözümlenmiş tahmin."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    horizon: Horizon
    as_of: datetime
    source: PredictionSource
    ensemble_version: str
    p_up: float
    y: int  # 1 = yukarı, 0 = aşağı
    brier: float
    hit: bool
    non_overlapping: bool
    confidence_label: ConfidenceLabel


# --- türev piyasa (Faz 3, ARCHITECTURE.md §4) ---


class FundingRate(BaseModel):
    """Gerçekleşmiş funding ödemesi (8 saatte bir)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    funding_time: datetime
    rate: float
    mark_price: float | None = None


class FundingLive(BaseModel):
    """Anlık funding göstergesi: son oran, sonraki ödeme zamanı, mark/index fiyatı."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    last_rate: float
    next_funding_time: datetime | None = None
    mark_price: float | None = None
    index_price: float | None = None


class OpenInterestPoint(BaseModel):
    """Açık pozisyon. `source`: 'hist' (5 dk ızgarası) veya 'live' (anlık okuma)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    oi: float
    oi_value_usd: float | None = None
    source: Literal["hist", "live"]


class LongShortPoint(BaseModel):
    """Long/short dağılımı. `kind`: global hesap, top hesap, top pozisyon."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    kind: Literal["global_account", "top_account", "top_position"]
    long_ratio: float
    short_ratio: float
    ratio: float


class TakerVolumePoint(BaseModel):
    """5 dakikalık taker alış/satış hacmi (CVD'nin REST yedeği)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    buy_vol: float
    sell_vol: float
    ratio: float


class Liquidation(BaseModel):
    """Tek bir zorunlu kapatma (forceOrder). `side`: kapanan pozisyonun yönü."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime
    side: Literal["long", "short"]
    qty: float
    price: float
    usd: float


class NewsItem(BaseModel):
    """Bir haber kaydı (`news_items`).

    `url_hash` kanonikleştirilmiş URL'in SHA-256'sıdır: aynı haber iki kaynaktan ya da izleme
    parametreleriyle gelse de tek satır olur. `id` yazmadan önce `None`; okurken doludur.
    `dedup_group_id` ve `is_group_head` dedup adımında (F4-2) doldurulur.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    source: str
    url: str
    url_hash: str
    title: str
    summary: str | None = None
    published_at: datetime
    fetched_at: datetime
    dedup_group_id: int | None = None
    is_group_head: bool = True
    raw_json: str | None = None


class FeedCursor(BaseModel):
    """Bir feed'in koşullu istek durumu: `ETag` / `Last-Modified` (ARCHITECTURE.md §4)."""

    model_config = ConfigDict(frozen=True)

    etag: str | None = None
    last_modified: str | None = None


class OrderflowRow(BaseModel):
    """Bir dakikalık order flow özeti (`orderflow_1m`).

    Alanlar iki kaynaktan gelir: işlem/likidasyon/top-20 değerlerini WS akışı, ±%1 derinliği REST
    anlık görüntüsü yazar. Bu yüzden `None` alanlar "bu kaynak yazmadı" demektir ve upsert sırasında
    diğer kaynağın yazdığı değeri **ezmez**.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: datetime  # dakikanın başlangıcı (UTC)
    buy_vol: float | None = None
    sell_vol: float | None = None
    cvd_delta: float | None = None
    trade_count: int | None = None
    liq_long_usd: float | None = None
    liq_short_usd: float | None = None
    liq_count: int | None = None
    top20_bid_qty: float | None = None
    top20_ask_qty: float | None = None
    top20_imbalance: float | None = None
    depth1pct_bid_usd: float | None = None
    depth1pct_ask_usd: float | None = None
    depth1pct_imbalance: float | None = None
    spread_bps: float | None = None
    coverage_seconds: float | None = None
