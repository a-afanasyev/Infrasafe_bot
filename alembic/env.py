from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from uk_management_bot.database.session import Base
from uk_management_bot.database.models import *  # noqa: F401,F403
# Регистрируем пилотные модели access_control на том же Base.metadata, чтобы
# autogenerate/target_metadata видел 18 таблиц домена контроля доступа (Ф2).
import access_control.domain  # noqa: F401,E402
from uk_management_bot.config.settings import settings

config = context.config

# Configure logging BEFORE overriding sqlalchemy.url
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata

# media_* исключаются из autogenerate/`alembic check` — SSOT-allowlist в helper'е,
# юнит-тестируемом без исполнения env.py (см. test_metadata_completeness.py).
from uk_management_bot.database.migration_include import include_object  # noqa: E402


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # PR-7 (F-01): переключение на uk_migration_owner, чтобы объекты, созданные
        # миграцией, принадлежали owner-роли, а не LOGIN-роли uk_migrator (иначе
        # ALTER DEFAULT PRIVILEGES FOR ROLE uk_migration_owner на них не подействует).
        # SESSION — scope по умолчанию для SET ROLE, переживает границы транзакций и
        # autocommit_block() (в отличие от LOCAL). Guard по migration_owner_exists —
        # backward-compat: три существующих CI job'а и dev Postgres эту роль не
        # провижинят, там миграция должна работать как раньше.
        require_owner = os.getenv("REQUIRE_MIGRATION_OWNER") == "1"
        # SQLAlchemy 2.x autobegin: этот SELECT сам открывает транзакцию на
        # connection, даже если migration_owner_exists окажется False. commit()
        # ниже — БЕЗУСЛОВНЫЙ, не только внутри ветки SET SESSION ROLE: забытый
        # commit() в backward-compat пути (роль не найдена, не обязательна)
        # оставляет эту транзакцию открытой до context.configure(), и Alembic,
        # переиспользуя её вместо своей, тихо не коммитит применённые миграции
        # (эмпирически воспроизведено: alembic upgrade head печатает "Running
        # upgrade" и завершается кодом 0, но alembic_version не создаётся).
        migration_owner_exists = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'uk_migration_owner'")
        ).scalar()
        if migration_owner_exists:
            connection.execute(text("SET SESSION ROLE uk_migration_owner"))
        elif require_owner:
            raise RuntimeError(
                "REQUIRE_MIGRATION_OWNER=1, но роль uk_migration_owner "
                "не найдена — provisioning не завершён, миграция остановлена"
            )
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
