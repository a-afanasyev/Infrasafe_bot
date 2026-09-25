"""Внутренние записи истории (is_internal) в бот-истории комментариев.

Решение владельца: «Проблему» исполнителя (и смену категории) видят только
сотрудники заявки — менеджер и её исполнитель; житель — нет. Раньше бот-
загрузчики истории не смотрели на is_internal вовсе и отдавали такие записи
заявителю.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers import request_comments as rc

NUMBER = "260925-003"
OWNER_TG, EXEC_TG, MANAGER_TG = 6001, 6002, 6003
PUBLIC, INTERNAL = "публичный-текст", "внутренняя-проблема"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def world(db):
    db.add_all([
        User(id=1, telegram_id=OWNER_TG, first_name="Житель", roles='["applicant"]',
             active_role="applicant", status="approved", language="ru"),
        User(id=2, telegram_id=EXEC_TG, first_name="Исполнитель", roles='["executor"]',
             active_role="executor", status="approved", language="ru"),
        User(id=3, telegram_id=MANAGER_TG, first_name="Менеджер", roles='["manager"]',
             active_role="manager", status="approved", language="ru"),
    ])
    db.commit()
    db.add(Request(request_number=NUMBER, user_id=1, executor_id=2, category="Электрика",
                   address="Дом 1", description="d", status="В работе"))
    db.commit()
    db.add_all([
        RequestComment(request_number=NUMBER, user_id=1, comment_text=PUBLIC,
                       comment_type="problem", is_internal=False),
        RequestComment(request_number=NUMBER, user_id=2, comment_text=INTERNAL,
                       comment_type="problem", is_internal=True),
    ])
    db.commit()


def _text(verdict_view) -> str:
    verdict, view = verdict_view
    assert verdict == "ok"
    return view.formatted_comments


@pytest.mark.parametrize("loader", [
    lambda db, tg: rc._load_comments_view(db, NUMBER, tg, "ru"),
    lambda db, tg: rc._load_all_comments_view(db, NUMBER, tg, "ru"),
    lambda db, tg: rc._load_comments_by_type_view(db, NUMBER, "problem", tg, "ru"),
])
def test_resident_does_not_see_internal(db, world, loader):
    text = _text(loader(db, OWNER_TG))
    assert PUBLIC in text and INTERNAL not in text


@pytest.mark.parametrize("tg", [EXEC_TG, MANAGER_TG])
@pytest.mark.parametrize("loader", [
    lambda db, tg: rc._load_comments_view(db, NUMBER, tg, "ru"),
    lambda db, tg: rc._load_all_comments_view(db, NUMBER, tg, "ru"),
    lambda db, tg: rc._load_comments_by_type_view(db, NUMBER, "problem", tg, "ru"),
])
def test_staff_of_request_sees_internal(db, world, loader, tg):
    text = _text(loader(db, tg))
    assert PUBLIC in text and INTERNAL in text
