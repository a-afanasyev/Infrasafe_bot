"""BUG-185: уведомления о групповом назначении доходят до ВСЕЙ группы.

`AssignmentService._notify_group_assignment` звал несуществующий
`NotificationService.send_notification` — AttributeError с рождения гасился
broad-except'ом, и исполнители БЕЗ активной смены не узнавали о заявке в своей
группе никогда (дежурным слал сам хендлер — другой канал). Решение владельца
2026-09-01: «заводи и чини». Уведомления консолидированы в
`auto_assign_request_by_category` (единственный живой вызывающий
`assign_to_group`): дежурным — прежний богатый наряд, остальным подходящим —
лёгкое уведомление о заявке в группе; оба — на языке ПОЛУЧАТЕЛЯ и с
html.escape пользовательских подстановок (канон BUG-174).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.helpers import get_text

NUMBER = "260901-002"
MANAGER_ID, ON_SHIFT_ID, OFF_SHIFT_ID, OTHER_SPEC_ID = 1, 2, 3, 4
ON_SHIFT_TG, OFF_SHIFT_TG, OTHER_SPEC_TG = 200, 300, 400


class _FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))

    def by_chat(self, chat_id):
        return [text for cid, text in self.sent if cid == chat_id]


@pytest.fixture()
def db():
    from uk_management_bot.database.session import Base
    import uk_management_bot.database.models  # noqa: F401 — все таблицы

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def bot(monkeypatch):
    fake = _FakeBot()
    monkeypatch.setattr(
        "uk_management_bot.services.notification_service._get_shared_bot",
        lambda: fake)
    return fake


def _seed(db, *, address="Дом 1", description="Не горит лампа"):
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.shift import Shift
    from uk_management_bot.database.models.user import User

    def user(uid, tg, *, roles='["executor"]', language="ru",
             specialization='["electrician"]'):
        db.add(User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="U",
                    roles=roles, status="approved", language=language,
                    specialization=specialization))

    user(MANAGER_ID, 100, roles='["manager"]', specialization=None)
    user(ON_SHIFT_ID, ON_SHIFT_TG)
    user(OFF_SHIFT_ID, OFF_SHIFT_TG, language="uz")
    user(OTHER_SPEC_ID, OTHER_SPEC_TG, specialization='["plumber"]')

    now = datetime.now()
    db.add(Shift(user_id=ON_SHIFT_ID, status="active",
                 start_time=now - timedelta(hours=1),
                 end_time=now + timedelta(hours=1)))

    req = Request(request_number=NUMBER, user_id=MANAGER_ID,
                  category="Электрика", description=description,
                  address=address, status="Новая")
    db.add(req)
    db.commit()
    return req


async def _run(db, request):
    from uk_management_bot.database.models.user import User
    from uk_management_bot.handlers.admin.shared import (
        auto_assign_request_by_category,
    )

    manager = db.get(User, MANAGER_ID)
    return await auto_assign_request_by_category(request, db, manager)


@pytest.mark.parametrize("language", ["ru", "uz"])
def test_group_notice_template_exists_in_both_locales(language):
    text = get_text("admin.handlers.new_request_for_group", language=language)
    assert not text.startswith("admin."), \
        f"нет шаблона new_request_for_group в локали {language}"
    assert "{request_number}" in text


class TestGroupAssignNotices:
    @pytest.mark.asyncio
    async def test_off_shift_matching_executor_is_notified(self, db, bot):
        """Ядро дефекта: исполнитель БЕЗ смены раньше не узнавал никогда."""
        request = _seed(db)
        from uk_management_bot.handlers.admin.shared import ASSIGN_OK

        assert await _run(db, request) == ASSIGN_OK
        texts = bot.by_chat(OFF_SHIFT_TG)
        assert len(texts) == 1, "исполнителю без смены — ровно одно уведомление"
        assert NUMBER in texts[0]

    @pytest.mark.asyncio
    async def test_off_shift_notice_is_in_recipient_language(self, db, bot):
        from uk_management_bot.handlers.shift_management.shared import (
            translate_specializations,
        )

        request = _seed(db)
        await _run(db, request)
        (text,) = bot.by_chat(OFF_SHIFT_TG)
        # Получатель в фикстуре uz: шаблон и подпись специализации — тоже uz.
        assert translate_specializations(["electrician"], "uz") in text
        assert get_text(
            "admin.handlers.new_request_for_group", language="uz"
        ).split("{", 1)[0] in text

    @pytest.mark.asyncio
    async def test_on_shift_executor_gets_duty_order_not_group_notice(self, db, bot):
        request = _seed(db)
        await _run(db, request)
        texts = bot.by_chat(ON_SHIFT_TG)
        assert len(texts) == 1, "дежурному — ровно одно (богатый наряд, без дубля)"
        assert "Не горит лампа" in texts[0], "наряд дежурного несёт описание"

    @pytest.mark.asyncio
    async def test_non_matching_executor_is_silent(self, db, bot):
        request = _seed(db)
        await _run(db, request)
        assert bot.by_chat(OTHER_SPEC_TG) == []

    @pytest.mark.asyncio
    async def test_user_substitutions_are_html_escaped(self, db, bot):
        """Канон BUG-174: сырой '<' в адресе давал Telegram-400 — уведомление
        молча терялось. Экранируются оба шаблона."""
        request = _seed(db, address="<Дом> & 1", description="a <b> c")
        await _run(db, request)
        for tg in (ON_SHIFT_TG, OFF_SHIFT_TG):
            (text,) = bot.by_chat(tg)
            assert "&lt;" in text and "<Дом>" not in text, text

    @pytest.mark.asyncio
    async def test_group_assignment_row_is_still_written(self, db, bot):
        from uk_management_bot.database.models.request_assignment import (
            RequestAssignment,
        )

        request = _seed(db)
        await _run(db, request)
        row = db.query(RequestAssignment).filter_by(
            request_number=NUMBER, status="active").one()
        assert row.assignment_type == "group"
        assert row.group_specialization == "electrician"


def test_assignment_service_has_no_call_to_nonexistent_method():
    """Пин класса BUG-148/155/160/174: вызовов `send_notification` (метода,
    которого у NotificationService нет) в assignment_service не осталось.

    AST, а не греп: надгробные комментарии имеют право называть метод."""
    import ast
    import inspect

    from uk_management_bot.services import assignment_service

    tree = ast.parse(inspect.getsource(assignment_service))
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "send_notification" not in calls
