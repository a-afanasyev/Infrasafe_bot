"""A9-P3-14: провенанс Group Intake — оба поля или ни одного.

Частичный уникальный индекс 0019 (`uq_requests_source_message`) держит
«одно сообщение группы — одна заявка» только когда `source_chat_id` задан:
при `source_chat_id IS NULL` NULL-ы в уникальном индексе не равны друг другу,
и дубли по одному `source_message_id` проходят. Миграция 0020 закрывает дыру
CHECK'ом `(source_message_id IS NULL) = (source_chat_id IS NULL)`; модель несёт
тот же CheckConstraint, чтобы `alembic check` не видел дрейфа.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTRAINT = "ck_requests_source_provenance_pair"


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


def _request(user_id: int, number: str, **provenance) -> Request:
    return Request(
        request_number=number, user_id=user_id, category="electricity",
        address="a", description="d", urgency="low", status="Новая",
        source="group", **provenance,
    )


@pytest.fixture()
def user(db):
    row = User(telegram_id=111, roles='["applicant"]', active_role="applicant",
               status="approved", language="ru")
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    "provenance",
    [
        {"source_chat_id": -100500, "source_message_id": None},
        {"source_chat_id": None, "source_message_id": 42},
    ],
)
def test_half_provenance_is_rejected(db, user, provenance):
    db.add(_request(user.id, "260923-001", **provenance))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    "provenance",
    [
        {"source_chat_id": -100500, "source_message_id": 42},
        {"source_chat_id": None, "source_message_id": None},
    ],
)
def test_full_or_empty_provenance_is_accepted(db, user, provenance):
    db.add(_request(user.id, "260923-002", **provenance))
    db.commit()


def test_model_declares_named_check():
    names = {c.name for c in Request.__table__.constraints}
    assert CONSTRAINT in names


def test_migration_020_is_head_and_adds_the_check():
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "020"
    revision = script.get_revision("020")
    assert revision.down_revision == "019"
    source = Path(revision.path).read_text(encoding="utf-8")
    assert CONSTRAINT in source
    assert "(source_message_id IS NULL) = (source_chat_id IS NULL)" in source
    assert "def downgrade" in source and "drop_constraint" in source
