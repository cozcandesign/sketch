"""Tahmin işi: snapshot → sinyal modülleri → ensemble → rapor → defter.

İki tür tahmin aynı anda yazılır:

- `source='live'`: gerçek sinyal modüllerinin ürettiği tahmin (Faz 2'de yalnızca teknik modül),
- `source='baseline'`: iki referans tahminci. Bunlar kalıcıdır; her modülün yenmesi gereken taban
  çizgisidir (ARCHITECTURE.md §11.4, K26).

Bir modül istisna fırlatırsa tahmin iptal edilmez: o modül "veri yok" sayılır, ensemble ağırlığını
diğerlerine dağıtır ve olay loglanır. Tek bir modülün hatası sistemi durdurmaz (CLAUDE.md §6).
"""

from collections.abc import Sequence
from datetime import datetime

from loguru import logger

from marketpulse.core.types import Horizon, Interval
from marketpulse.ensemble import expected_range
from marketpulse.ensemble.combine import ENSEMBLE_VERSION, clip_probability, combine
from marketpulse.ensemble.confidence import evaluate
from marketpulse.ensemble.weights import load_default_weights
from marketpulse.features.feature_store import FeatureStore
from marketpulse.features.snapshot import FeatureSnapshot
from marketpulse.reporting.build import build_report
from marketpulse.signals.base import SignalModule, SignalResult, no_data
from marketpulse.signals.technical import TechnicalModule
from marketpulse.storage.models import NewPrediction, SignalRow
from marketpulse.storage.repository import Repository
from marketpulse.tracking import baselines
from marketpulse.tracking.ledger import Ledger, is_non_overlapping

PRICE_INTERVAL = Interval.M1  # K16: gerçek sonuç ve başlangıç fiyatı spot 1 dk kapanışından
BASELINE_CONFIDENCE = 0.2
EXPANSION_LEVEL = 0.8  # vol_regime ölçeği: -1 sıkışma, +1 genişleme


def default_modules() -> tuple[SignalModule, ...]:
    """Faz 2'de tek modül. Sonraki fazlar bu listeye ekler."""
    return (TechnicalModule(),)


class LivePredictor:
    """Canlı tahmin üretir. Ağırlıkları DB'den okur, yoksa YAML varsayılanına düşer."""

    def __init__(
        self,
        repo: Repository,
        ledger: Ledger,
        store: FeatureStore,
        modules: Sequence[SignalModule] | None = None,
    ) -> None:
        self._repo = repo
        self._ledger = ledger
        self._store = store
        self._modules = tuple(modules) if modules is not None else default_modules()
        self._defaults = load_default_weights()

    async def run(self, *, symbols: Sequence[str], horizon: Horizon, as_of: datetime) -> int:
        """Her sembol için bir canlı tahmin yazar. Yazılan tahmin sayısını döner."""
        weights = await self._weights(horizon)
        written = 0
        for symbol in symbols:
            snapshot = await self._store.snapshot(symbol, as_of)
            if snapshot.price is None:
                logger.bind(symbol=symbol, horizon=horizon.value).debug(
                    "fiyat mumu yok, canlı tahmin atlandı"
                )
                continue
            await self._write(snapshot, horizon, weights, price=snapshot.price)
            written += 1
        return written

    async def _weights(self, horizon: Horizon) -> dict[str, float]:
        stored = await self._repo.get_weights(horizon)
        return stored or dict(self._defaults[horizon])

    async def _write(
        self,
        snapshot: FeatureSnapshot,
        horizon: Horizon,
        weights: dict[str, float],
        *,
        price: float,
    ) -> None:
        results = [self._run_module(module, snapshot, horizon) for module in self._modules]
        ensemble = combine(results, weights, horizon=horizon)
        confidence = evaluate(
            results,
            ensemble.effective_weights,
            conflict_active=ensemble.conflict.active,
            breadth=ensemble.weight_mass,
            high_volatility=_regime(results) >= EXPANSION_LEVEL,
        )
        expected = expected_range.estimate(
            snapshot, horizon, expansion=_regime(results) >= EXPANSION_LEVEL
        )
        report = build_report(
            symbol=snapshot.symbol,
            horizon=horizon,
            results=results,
            ensemble=ensemble,
            confidence=confidence,
            expected=expected,
        )
        await self._ledger.record(
            NewPrediction(
                symbol=snapshot.symbol,
                horizon=horizon,
                as_of=snapshot.as_of,
                target_at=snapshot.as_of + horizon.length,
                price_at=price,
                p_up=clip_probability(ensemble.p_up),
                expected_low=None if expected is None else expected.low,
                expected_high=None if expected is None else expected.high,
                confidence=confidence.value,
                confidence_label=confidence.label,
                conflict=ensemble.conflict.active,
                veto_active=False,  # veto Faz 4 (haber) ve Faz 5 (takvim) ile gelir
                combined_score=ensemble.combined_score,
                weights=dict(ensemble.effective_weights),
                ensemble_version=ENSEMBLE_VERSION,
                non_overlapping=is_non_overlapping(snapshot.as_of, horizon),
                source="live",
                report=report,
            ),
            [_signal_row(result) for result in results],
        )

    def _run_module(
        self, module: SignalModule, snapshot: FeatureSnapshot, horizon: Horizon
    ) -> SignalResult:
        """Modülü çalıştırır; istisnayı "veri yok"a çevirir ve loglar."""
        try:
            return module.compute(snapshot, horizon)
        except Exception as exc:  # modül hatası tahmini iptal etmez
            logger.bind(symbol=snapshot.symbol, horizon=horizon.value, module=module.name).warning(
                "modül hata verdi, veri yok sayılıyor: {err}", err=exc
            )
            return no_data(module.name, snapshot.as_of)


def _signal_row(result: SignalResult) -> SignalRow:
    return SignalRow(
        module=result.module,
        score=result.score,
        confidence=result.confidence,
        coverage=result.coverage,
        components=dict(result.components),
        rationale=list(result.rationale),
        data_as_of=result.data_as_of,
    )


def _regime(results: Sequence[SignalResult]) -> float:
    """Modüllerin bildirdiği en uç volatilite rejimi (−1 sıkışma … +1 genişleme)."""
    values = [
        result.components["vol_regime"] for result in results if "vol_regime" in result.components
    ]
    return max(values, key=abs) if values else 0.0


async def run_baseline_predictions(
    repo: Repository,
    ledger: Ledger,
    *,
    symbols: Sequence[str],
    horizon: Horizon,
    as_of: datetime,
) -> int:
    """Her sembol için iki referans tahmini yazar. Yazılan tahmin sayısını döner."""
    written = 0
    for symbol in symbols:
        candle = await repo.latest_candle(symbol, PRICE_INTERVAL, as_of=as_of)
        if candle is None:
            logger.bind(symbol=symbol, horizon=horizon.value).debug(
                "fiyat mumu yok, tahmin atlandı"
            )
            continue
        for result in (
            await baselines.climatology(repo, symbol, horizon, as_of),
            await baselines.momentum(repo, symbol, horizon, as_of),
        ):
            await ledger.record(
                NewPrediction(
                    symbol=symbol,
                    horizon=horizon,
                    as_of=as_of,
                    target_at=as_of + horizon.length,
                    price_at=candle.close,
                    p_up=clip_probability(result.p_up),
                    confidence=BASELINE_CONFIDENCE,
                    confidence_label="low",
                    ensemble_version=result.version,
                    non_overlapping=is_non_overlapping(as_of, horizon),
                    source="baseline",
                    report={
                        "headline": f"{symbol} · {horizon.label_tr} · referans tahmin",
                        "reasons": [{"module": "baseline", "text": result.note_tr}],
                        "samples": result.samples,
                    },
                )
            )
            written += 1
    return written
