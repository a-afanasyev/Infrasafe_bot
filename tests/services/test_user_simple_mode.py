"""Простой режим исполнителя: флаг `users.simple_mode` (миграция 021).

Флаг на человека, включает менеджер; дефолт false — существующие строки и
новые пользователи остаются в старой панели. Миграция — ADD COLUMN с
server_default, модель несёт тот же server_default, чтобы `alembic check` не
видел дрейфа.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_new_user_defaults_to_simple_mode_off(db):
    user = User(telegram_id=7001, roles='["executor"]', active_role="executor")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.simple_mode is False


def test_model_column_is_not_null_with_server_default():
    column = User.__table__.c.simple_mode
    assert column.nullable is False
    assert column.server_default is not None


def test_migration_021_is_head_and_adds_the_column():
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "021"
    revision = script.get_revision("021")
    assert revision.down_revision == "020"
    source = Path(revision.path).read_text(encoding="utf-8")
    assert '"simple_mode"' in source
    assert "server_default=sa.false()" in source
    assert "nullable=False" in source
    assert "def downgrade" in source and "drop_column" in source
