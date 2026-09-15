"""Tüm tablolar (ARCHITECTURE.md §6). SQLAlchemy Core; ORM yok.

JSON alanları `_json` son ekiyle TEXT. Zamanlar UTCDateTime. Fiyat/oran Float.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

from marketpulse.storage.types import UTCDateTime

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# --- 6.1 Piyasa verisi -------------------------------------------------------------------

candles = Table(
    "candles",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("interval", String(4), primary_key=True),
    Column("open_time", UTCDateTime, primary_key=True),
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
    Column("volume", Float, nullable=False),
    Column("quote_volume", Float, nullable=False),
    Column("trades", Integer, nullable=False),
    Column("taker_buy_base", Float, nullable=False),
    Column("close_time", UTCDateTime, nullable=False),
    Index("ix_candles_symbol_interval_close_time", "symbol", "interval", "close_time"),
)

funding_rates = Table(
    "funding_rates",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("funding_time", UTCDateTime, primary_key=True),
    Column("rate", Float, nullable=False),
    Column("mark_price", Float),
)

funding_live = Table(
    "funding_live",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("ts", UTCDateTime, primary_key=True),
    Column("last_rate", Float, nullable=False),
    Column("next_funding_time", UTCDateTime),
    Column("mark_price", Float),
    Column("index_price", Float),
)

open_interest = Table(
    "open_interest",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("ts", UTCDateTime, primary_key=True),
    Column("oi", Float, nullable=False),
    Column("oi_value_usd", Float),
    Column("source", String(8), nullable=False),  # 'hist' | 'live'
)

long_short_ratio = Table(
    "long_short_ratio",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("ts", UTCDateTime, primary_key=True),
    Column("kind", String(16), primary_key=True),  # global_account | top_account | top_position
    Column("long_ratio", Float, nullable=False),
    Column("short_ratio", Float, nullable=False),
    Column("ratio", Float, nullable=False),
)

taker_volume = Table(
    "taker_volume",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("ts", UTCDateTime, primary_key=True),
    Column("buy_vol", Float, nullable=False),
    Column("sell_vol", Float, nullable=False),
    Column("ratio", Float, nullable=False),
)

orderflow_1m = Table(
    "orderflow_1m",
    metadata,
    Column("symbol", String(20), primary_key=True),
    Column("ts", UTCDateTime, primary_key=True),
    Column("buy_vol", Float, nullable=False, default=0.0),
    Column("sell_vol", Float, nullable=False, default=0.0),
    Column("cvd_delta", Float, nullable=False, default=0.0),
    Column("trade_count", Integer, nullable=False, default=0),
    Column("liq_long_usd", Float, nullable=False, default=0.0),
    Column("liq_short_usd", Float, nullable=False, default=0.0),
    Column("liq_count", Integer, nullable=False, default=0),
    Column("top20_bid_qty", Float),
    Column("top20_ask_qty", Float),
    Column("top20_imbalance", Float),
    Column("depth1pct_bid_usd", Float),
    Column("depth1pct_ask_usd", Float),
    Column("depth1pct_imbalance", Float),
    Column("spread_bps", Float),
    Column("coverage_seconds", Float, nullable=False, default=0.0),
)

liquidations = Table(
    "liquidations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(20), nullable=False),
    Column("ts", UTCDateTime, nullable=False),
    Column("side", String(5), nullable=False),  # long | short
    Column("qty", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("usd", Float, nullable=False),
    Index("ix_liquidations_symbol_ts", "symbol", "ts"),
)

# --- 6.2 Haber, kademeler ve makro -------------------------------------------------------

news_items = Table(
    "news_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source", String(32), nullable=False),
    Column("url", Text, nullable=False),
    Column("url_hash", String(64), nullable=False, unique=True),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    Column("published_at", UTCDateTime, nullable=False),
    Column("fetched_at", UTCDateTime, nullable=False),
    Column("dedup_group_id", Integer),
    Column("is_group_head", Boolean, nullable=False, default=True),
    Column("raw_json", Text),
    Index("ix_news_items_published_at", "published_at"),
    Index("ix_news_items_dedup_group_id", "dedup_group_id"),
)

news_tier1 = Table(
    "news_tier1",
    metadata,
    Column("news_id", Integer, ForeignKey("news_items.id", ondelete="CASCADE"), primary_key=True),
    Column("model", String(64), nullable=False),
    Column("classified_at", UTCDateTime, nullable=False),
    Column("category", String(16), nullable=False),
    Column("affected_json", Text, nullable=False),
    Column("tone", Float, nullable=False),
    Column("importance", Float, nullable=False),
    Column("summary_tr", Text),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("cache_read_tokens", Integer, nullable=False, default=0),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("inherited_from", Integer),
)

news_tier2 = Table(
    "news_tier2",
    metadata,
    Column("news_id", Integer, ForeignKey("news_items.id", ondelete="CASCADE"), primary_key=True),
    Column("model", String(64), nullable=False),
    Column("classified_at", UTCDateTime, nullable=False),
    Column("impact", Integer, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("horizon", String(16), nullable=False),
    Column("priced_in", Float, nullable=False),
    Column("credibility", String(16), nullable=False),
    Column("second_order_tr", Text),
    Column("precedent_tr", Text),
    Column("rationale_tr", Text),
    Column("affected_json", Text, nullable=False),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("cache_read_tokens", Integer, nullable=False, default=0),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("inherited_from", Integer),
)

news_outcomes = Table(
    "news_outcomes",
    metadata,
    Column("news_id", Integer, ForeignKey("news_items.id", ondelete="CASCADE"), primary_key=True),
    Column("symbol", String(20), primary_key=True),
    Column("horizon", String(4), primary_key=True),  # 1h | 4h | 24h
    Column("price_at_publish", Float, nullable=False),
    Column("price_after", Float, nullable=False),
    Column("realized_return", Float, nullable=False),
    Column("resolved_at", UTCDateTime, nullable=False),
    Column("tier_reached", Integer, nullable=False),
    Column("predicted_sign", Integer, nullable=False),
    Column("hit", Boolean),
)

fear_greed = Table(
    "fear_greed",
    metadata,
    Column("date", String(10), primary_key=True),  # YYYY-MM-DD (UTC)
    Column("value", Integer, nullable=False),
    Column("label", String(32)),
    Column("available_at", UTCDateTime, nullable=False),
)

macro_daily = Table(
    "macro_daily",
    metadata,
    Column("ticker", String(16), primary_key=True),
    Column("date", String(10), primary_key=True),
    Column("open", Float),
    Column("high", Float),
    Column("low", Float),
    Column("close", Float, nullable=False),
    Column("available_at", UTCDateTime, nullable=False),
)

calendar_events = Table(
    "calendar_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("scheduled_at", UTCDateTime, nullable=False),
    Column("importance", Integer, nullable=False),
    Column("note", Text),
    Column("source", String(32), nullable=False, default="yaml"),
    Index("ix_calendar_events_scheduled_at", "scheduled_at"),
)

# --- 6.3 Tahmin defteri ------------------------------------------------------------------

predictions = Table(
    "predictions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(20), nullable=False),
    Column("horizon", String(4), nullable=False),
    Column("as_of", UTCDateTime, nullable=False),
    Column("target_at", UTCDateTime, nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
    Column("price_at", Float, nullable=False),
    Column("p_up", Float, nullable=False),
    Column("expected_low", Float),
    Column("expected_high", Float),
    Column("confidence", Float, nullable=False),
    Column("confidence_label", String(4), nullable=False),  # low | mid | high
    Column("conflict", Boolean, nullable=False, default=False),
    Column("veto_active", Boolean, nullable=False, default=False),
    Column("veto_reason", Text),
    Column("combined_score", Float),
    Column("weights_json", Text),
    Column("ensemble_version", String(16), nullable=False),
    Column("non_overlapping", Boolean, nullable=False, default=False),
    Column("source", String(8), nullable=False),  # live | baseline | backtest
    Column("run_id", String(32)),
    Column("report_json", Text),
    Index("ix_predictions_symbol_horizon_as_of", "symbol", "horizon", "as_of"),
    Index("ix_predictions_target_at", "target_at"),
    Index("ix_predictions_source_run_id", "source", "run_id"),
)

prediction_signals = Table(
    "prediction_signals",
    metadata,
    Column(
        "prediction_id",
        Integer,
        ForeignKey("predictions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("module", String(16), primary_key=True),
    Column("score", Float, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("coverage", Float, nullable=False),
    Column("components_json", Text),
    Column("rationale_json", Text),
    Column("data_as_of", UTCDateTime),
)

prediction_outcomes = Table(
    "prediction_outcomes",
    metadata,
    Column(
        "prediction_id",
        Integer,
        ForeignKey("predictions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("resolved_at", UTCDateTime, nullable=False),
    Column("price_at_target", Float),
    Column("realized_return", Float),
    Column("outcome", String(10), nullable=False),  # up | down | unresolved
    Column("hit", Boolean),
    Column("brier", Float),
    Column("resolved_by", String(16), nullable=False),
)

# --- 6.4 Kalibrasyon ve ağırlıklar -------------------------------------------------------

module_calibration = Table(
    "module_calibration",
    metadata,
    Column("module", String(16), primary_key=True),
    Column("horizon", String(4), primary_key=True),
    Column("fitted_at", UTCDateTime, nullable=False),
    Column("a", Float, nullable=False),
    Column("b", Float, nullable=False),
    Column("n", Integer, nullable=False),
    Column("brier", Float),
    Column("hit_rate", Float),
    Column("hit_rate_ci_low", Float),
    Column("hit_rate_ci_high", Float),
)

calibration_bins = Table(
    "calibration_bins",
    metadata,
    Column("horizon", String(4), primary_key=True),
    Column("subset", String(16), primary_key=True),
    Column("bin", Integer, primary_key=True),
    Column("computed_at", UTCDateTime, nullable=False),
    Column("n", Integer, nullable=False),
    Column("mean_p", Float),
    Column("observed_freq", Float),
)

metrics_daily = Table(
    "metrics_daily",
    metadata,
    Column("date", String(10), primary_key=True),
    Column("symbol", String(20), primary_key=True),  # 'ALL' toplam için
    Column("horizon", String(4), primary_key=True),
    Column("subset", String(16), primary_key=True),
    Column("n", Integer, nullable=False),
    Column("brier", Float),
    Column("brier_skill", Float),
    Column("hit_rate", Float),
    Column("base_rate", Float),
)

news_tier_metrics = Table(
    "news_tier_metrics",
    metadata,
    Column("tier", Integer, primary_key=True),
    Column("horizon", String(4), primary_key=True),
    Column("window", String(8), primary_key=True),
    Column("computed_at", UTCDateTime, nullable=False),
    Column("n", Integer, nullable=False),
    Column("hit_rate", Float),
    Column("ci_low", Float),
    Column("ci_high", Float),
    Column("cost_usd", Float, nullable=False, default=0.0),
)

weights = Table(
    "weights",
    metadata,
    Column("horizon", String(4), primary_key=True),
    Column("module", String(16), primary_key=True),
    Column("weight", Float, nullable=False),
    Column("valid_from", UTCDateTime, nullable=False),
    Column("source", String(8), nullable=False),  # default | applied
    Column("proposal_id", Integer),
)

weight_proposals = Table(
    "weight_proposals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("horizon", String(4), nullable=False),
    Column("current_json", Text, nullable=False),
    Column("proposed_json", Text, nullable=False),
    Column("based_on_n", Integer, nullable=False),
    Column("metrics_json", Text),
    Column("status", String(8), nullable=False, default="pending"),
    Column("decided_at", UTCDateTime),
)

weekly_reports = Table(
    "weekly_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("week_start", String(10), nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("report_json", Text, nullable=False),
    Column("summary_tr", Text, nullable=False),
)

# --- 6.5 İşletim -------------------------------------------------------------------------

alerts = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("symbol", String(20)),
    Column("kind", String(32), nullable=False),
    Column("severity", String(8), nullable=False),  # info | warn | critical
    Column("title", Text, nullable=False),
    Column("body", Text),
    Column("payload_json", Text),
    Column("dedup_key", String(128), nullable=False),
    Column("acknowledged_at", UTCDateTime),
    Index("ix_alerts_created_at", "created_at"),
    Index("ix_alerts_acknowledged_at", "acknowledged_at"),
)

settings_table = Table(
    "settings",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value_json", Text, nullable=False),
    Column("updated_at", UTCDateTime, nullable=False),
)

events_outbox = Table(
    "events_outbox",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("topic", String(32), nullable=False),
    Column("payload_json", Text, nullable=False),
    Index("ix_events_outbox_created_at", "created_at"),
)

llm_usage = Table(
    "llm_usage",
    metadata,
    Column("date", String(10), primary_key=True),
    Column("model", String(64), primary_key=True),
    Column("tier", Integer, primary_key=True),
    Column("calls", Integer, nullable=False, default=0),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("cache_read_tokens", Integer, nullable=False, default=0),
    Column("cost_usd", Float, nullable=False, default=0.0),
)

llm_budget_state = Table(
    "llm_budget_state",
    metadata,
    Column("id", Integer, primary_key=True),  # her zaman 1
    Column("date", String(10), nullable=False),
    Column("spent_usd", Float, nullable=False, default=0.0),
    Column("tier2_disabled_at", UTCDateTime),
    Column("tier1_disabled_at", UTCDateTime),
)

collector_health = Table(
    "collector_health",
    metadata,
    Column("collector", String(32), primary_key=True),
    Column("status", String(16), nullable=False),
    Column("last_success_at", UTCDateTime),
    Column("last_error_at", UTCDateTime),
    Column("last_error", Text),
    Column("consecutive_failures", Integer, nullable=False, default=0),
)

engine_heartbeat = Table(
    "engine_heartbeat",
    metadata,
    Column("id", Integer, primary_key=True),  # her zaman 1
    Column("ts", UTCDateTime, nullable=False),
    Column("version", String(16), nullable=False),
)

ALL_TABLES: tuple[str, ...] = tuple(metadata.tables.keys())
