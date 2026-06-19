"""Тесты модели Feedback (Task 1).

Проверяют дефолты ПОСЛЕ insert (Column(default=...) применяется при INSERT,
а не в конструкторе) и базовую запись/чтение.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.feedback import Feedback


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    user = User(
        id=1, telegram_id=111, username="u", first_name="U",
        roles='["applicant"]', active_role="applicant", status="approved", language="ru",
    )
    session.add(user)
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_defaults_applied_on_insert(db):
    fb = Feedback(user_id=1, type="complaint", text="Лифт не работает уже неделю")
    db.add(fb)
    db.commit()
    db.refresh(fb)
    # Дефолты проверяем ТОЛЬКО после commit/refresh
    assert fb.id is not None
    assert fb.status == "new"
    assert fb.source == "bot"
    assert fb.media_files == []
    assert fb.reply is None
    assert fb.created_at is not None


def test_explicit_fields_persist(db):
    fb = Feedback(
        user_id=1, type="wish", text="Хотелось бы больше зелени во дворе",
        source="twa", status="in_review", media_files=[42],
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    assert fb.type == "wish"
    assert fb.source == "twa"
    assert fb.status == "in_review"
    assert fb.media_files == [42]
