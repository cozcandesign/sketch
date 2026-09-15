"""loguru kurulumu. stdlib logging (uvicorn, sqlalchemy) loguru'ya yönlendirilir."""

import logging
import sys
from types import FrameType

from loguru import logger


class _InterceptHandler(logging.Handler):
    """stdlib log kayıtlarını loguru'ya aktarır."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str = "INFO", *, process: str = "marketpulse") -> None:
    """Tek stderr sink, yapılandırılmış alanlar için `extra` kullanılır.

    Log satırı biçimi: zaman | seviye | süreç | modül:satır | mesaj | extra alanlar.
    Anahtarlar hiçbir zaman loglanmaz (CLAUDE.md §13); SecretStr bunu zaten gizler.
    """
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
        f"{process} | <cyan>{{name}}</cyan>:<cyan>{{line}}</cyan> | {{message}} | {{extra}}"
    )
    logger.add(sys.stderr, level=level.upper(), format=fmt, enqueue=False, backtrace=False)
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).handlers = [_InterceptHandler()]
        logging.getLogger(noisy).propagate = False
