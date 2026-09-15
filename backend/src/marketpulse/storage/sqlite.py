"""SQLite repository: mixin'lerin birleşimi (ARCHITECTURE.md §6).

Bölünme yalnızca dosya boyutu içindir; dışarıya tek sınıf görünür.
"""

from marketpulse.storage.sqlite_candles import CandlesMixin
from marketpulse.storage.sqlite_ledger import LedgerMixin
from marketpulse.storage.sqlite_ops import OpsMixin


class SqliteRepository(OpsMixin, CandlesMixin, LedgerMixin):
    """`Repository` protokolünün SQLite gerçekleştirimi."""
