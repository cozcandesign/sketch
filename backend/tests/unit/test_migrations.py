"""Alembic migration'ları metadata ile birebir aynı tabloları üretmeli."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from marketpulse.storage.tables import ALL_TABLES, metadata

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_upgrade_head_creates_all_tables_and_downgrade_drops_them(tmp_path: Path) -> None:
    db_path = tmp_path / "mig.db"
    cfg = _config(db_path)
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    names = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert names == set(ALL_TABLES)
    command.downgrade(cfg, "base")
    names_after = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert names_after == set()
    engine.dispose()


def test_no_pending_autogenerate_changes(tmp_path: Path) -> None:
    """Metadata ile migration arasında fark yoksa autogenerate boş çıkmalı."""
    db_path = tmp_path / "cmp.db"
    command.upgrade(_config(db_path), "head")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, metadata)
    engine.dispose()
    assert diff == [], f"migration metadata'nın gerisinde: {diff}"
