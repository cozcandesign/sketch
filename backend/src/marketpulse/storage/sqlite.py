"""SQLite repository: mixin'lerin birleşimi (ARCHITECTURE.md §6).

Bölünme yalnızca dosya boyutu içindir; dışarıya tek sınıf görünür.
"""

from marketpulse.storage.sqlite_candles import CandlesMixin
from marketpulse.storage.sqlite_ledger import LedgerMixin
from marketpulse.storage.sqlite_ops import OpsMixin
from marketpulse.storage.sqlite_orderflow import OrderflowMixin
from marketpulse.storage.sqlite_weights import WeightsMixin


class SqliteRepository(OpsMixin, CandlesMixin, LedgerMixin, WeightsMixin, OrderflowMixin):
    """`Repository` protokolünün SQLite gerçekleştirimi."""
