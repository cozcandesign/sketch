"""Alembic ortamı: senkron sqlite sürücüsüyle, metadata `marketpulse.storage.tables`."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from marketpulse.config import Settings, find_env_file
from marketpulse.storage.tables import metadata
from marketpulse.storage.types import UTCDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _resolve_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    if "db_url" in x_args:
        return x_args["db_url"]
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return Settings(_env_file=find_env_file()).sync_db_url


def _render_item(type_: str, obj: object, _autogen_context: object) -> str | bool:
    """Migration dosyaları uygulama tipine bağımlı olmasın.

    UTCDateTime -> sa.DateTime(timezone=True) olarak yazılır.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            # Uygulama ile aynı mod: WAL'a geçiş burada, eşzamanlı bağlantı yokken yapılır.
            connection.exec_driver_sql("PRAGMA busy_timeout=5000")
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.commit()  # autobegin'i kapat; alembic kendi transaction'ını yönetsin
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
