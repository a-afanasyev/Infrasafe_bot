"""A9-P2-2: пользовательский ввод в HTML-сообщениях бота экранируется.

Бот шлёт с parse_mode=HTML по умолчанию. Сырое описание/примечание заявки или
имя из Telegram-профиля давали stored-инъекцию (``<a href>`` — живая ссылка в
карточке менеджера), а одиночный ``<``/``&`` — Telegram-400: карточка не
открывалась вовсе. Канон BUG-174/178 — ``html.escape`` в точке вывода.

Тесты бьют по живым хендлерам на sqlite; застаблен только Telegram-вызов
(``edit_text``) — проверяется ровно тот текст, что ушёл бы в Bot API.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.utils.datetime_utils import utc_now

EVIL = '<b>x</b> & <a href="https://evil">y</a>'
NUMBER = "260922-001"
MANAGER_TG, APPLICANT_TG, EXECUTOR_TG = 900100, 900200, 900300


@pytest.fixture()
def db():
    import uk_management_bot.database.models  # noqa: F401 — все таблицы

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _callback(data: str, telegram_id: int = MANAGER_TG):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = telegram_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _sent_text(cb) -> str:
    cb.message.edit_text.assert_awaited()
    call = cb.message.edit_text.await_args
    return call.args[0] if call.args else call.kwargs["text"]


def _assert_escaped(text: str) -> None:
    assert "<a href" not in text, text
    assert "<b>x</b>" not in text, text
    assert "&lt;" in text and "&amp;" in text, text


# ══════════════════════════════════════════════════════════════════════════
# Карточка заявки менеджера (handlers/admin/views.py)
# ══════════════════════════════════════════════════════════════════════════

class TestManagerRequestCard:
    def _seed(self, db):
        manager = User(id=1, telegram_id=MANAGER_TG, first_name="Mgr",
                       roles='["manager"]', active_role="manager",
                       status="approved")
        applicant = User(id=2, telegram_id=APPLICANT_TG,
                         first_name="Иван & <i>Ко</i>", last_name=None,
                         roles='["applicant"]', active_role="applicant",
                         status="approved")
        db.add_all([manager, applicant])
        db.flush()
        db.add(Request(
            request_number=NUMBER, user_id=2, category="electrics",
            status="Новая", description=EVIL, urgency="medium",
            address="Дом <1> & корпус", notes="уточнение: a < b & c",
            created_at=datetime.now(timezone.utc),
            is_returned=False, manager_confirmed=False))
        db.commit()
        return manager

    @pytest.mark.asyncio
    async def test_user_input_is_escaped_in_card(self, db, monkeypatch):
        from uk_management_bot.handlers.admin import views

        manager = self._seed(db)
        # Фотоотчёт тянется из media-service — сеть тесту не нужна.
        monkeypatch.setattr(views, "get_completion_media_file_ids",
                            AsyncMock(return_value=[]))
        cb = _callback(f"mview_{NUMBER}")
        await views.handle_manager_view_request(
            cb, db=db, roles=["manager"], active_role="manager",
            user=manager, language="ru")

        cb.answer.assert_not_awaited()  # не ушли в ветку «Произошла ошибка»
        text = _sent_text(cb)
        _assert_escaped(text)
        assert "&lt;b&gt;x&lt;/b&gt;" in text
        assert "Дом &lt;1&gt; &amp; корпус" in text
        assert "a &lt; b &amp; c" in text
        assert "Иван &amp; &lt;i&gt;Ко&lt;/i&gt;" in text
        assert "None" not in text


# ══════════════════════════════════════════════════════════════════════════
# Модерация квартир (handlers/address_moderation.py)
# ══════════════════════════════════════════════════════════════════════════

class TestApartmentModerationDetails:
    def _seed(self, db):
        from uk_management_bot.database.models import (
            Apartment, Building, UserApartment, Yard,
        )

        resident = User(id=2, telegram_id=APPLICANT_TG,
                        first_name="Том & Джерри", last_name=None,
                        username="tom<script>", roles='["applicant"]',
                        status="approved")
        db.add(resident)
        yard = Yard(name="Двор <A> & B")
        db.add(yard)
        db.flush()
        building = Building(address="Улица <5> & 7", yard_id=yard.id)
        db.add(building)
        db.flush()
        apartment = Apartment(building_id=building.id, apartment_number="12")
        db.add(apartment)
        db.flush()
        ua = UserApartment(user_id=resident.id, apartment_id=apartment.id,
                           status="pending")
        db.add(ua)
        db.commit()
        return ua.id

    @pytest.mark.asyncio
    async def test_resident_name_and_address_escaped(self, db):
        from uk_management_bot.handlers import address_moderation

        ua_id = self._seed(db)
        cb = _callback(f"addr_moderation_view:{ua_id}")
        await address_moderation.show_moderation_details(
            cb, AsyncMock(), language="ru", _db=db)

        text = _sent_text(cb)
        assert "Том &amp; Джерри" in text, text
        assert "Том & Джерри" not in text
        assert "tom&lt;script&gt;" in text and "<script>" not in text
        assert "Улица &lt;5&gt; &amp; 7" in text
        assert "Двор &lt;A&gt; &amp; B" in text
        assert "None" not in text


# ══════════════════════════════════════════════════════════════════════════
# Смены: назначение и отчёт по нагрузке (handlers/shift_management/*)
# ══════════════════════════════════════════════════════════════════════════

def _scope(session):
    @contextmanager
    def fake(_):
        yield session
    return fake


class TestShiftTexts:
    def _users(self, db):
        manager = User(id=5, telegram_id=MANAGER_TG, first_name="Mgr",
                       roles='["manager"]', status="approved", language="ru")
        executor = User(id=1, telegram_id=EXECUTOR_TG, first_name="<b>Ива&н</b>",
                        last_name=None, username="u1", roles='["executor"]',
                        status="approved", language="ru",
                        specialization='["electric"]')
        db.add_all([manager, executor])
        db.commit()
        return manager, executor

    @pytest.mark.asyncio
    async def test_assign_success_escapes_executor_name(self, db):
        from uk_management_bot.handlers.shift_management import assignment_b

        manager, _ = self._users(db)
        start = utc_now() + timedelta(days=1)
        db.add(Shift(id=10, start_time=start, end_time=start + timedelta(hours=8),
                     status="scheduled", specialization_focus=["electric"]))
        db.commit()

        cb = _callback("assign_executor_to_shift:10:1")
        with patch("uk_management_bot.services.notification_service.shifts.send_to_user",
                   AsyncMock(return_value=True)):
            await assignment_b.handle_assign_executor_to_shift(
                cb, MagicMock(), db=db, user=manager, roles=["manager"])

        text = _sent_text(cb)
        assert "&lt;b&gt;Ива&amp;н&lt;/b&gt;" in text, text
        assert "<b>Ива" not in text
        assert "None" not in text, "имя без фамилии давало «Иван None»"

    @pytest.mark.asyncio
    async def test_workload_report_escapes_names(self, db, monkeypatch):
        from uk_management_bot.handlers.shift_management import assignment_a
        from uk_management_bot.services.shift_management_service import (
            ShiftManagementService,
        )

        manager, executor = self._users(db)
        monkeypatch.setattr(assignment_a, "_db_scope", _scope(db))
        monkeypatch.setattr(assignment_a, "get_user_language", lambda *a, **k: "ru")
        # SQL-агрегат с extract(epoch) — PG-only; стабим строку статистики
        # уровнем ниже хендлера, текст собирает сам хендлер.
        stat = SimpleNamespace(id=1, first_name="Пётр & <u>Сын</u>", last_name=None,
                               shift_count=2, total_hours=16.0)
        monkeypatch.setattr(ShiftManagementService, "get_executor_workload_stats",
                            lambda self, *a: [stat])
        monkeypatch.setattr(ShiftManagementService, "list_executors_without_shifts",
                            lambda self, ids: [executor])

        cb = _callback("workload_analysis")
        await assignment_a.handle_workload_analysis(
            cb, MagicMock(), db=db, user=manager, roles=["manager"])

        text = _sent_text(cb)
        assert "Пётр &amp; &lt;u&gt;Сын&lt;/u&gt;" in text, text
        assert "&lt;b&gt;Ива&amp;н&lt;/b&gt;" in text, text
        assert "<u>Сын</u>" not in text and "<b>Ива" not in text
        assert "None" not in text

    @pytest.mark.asyncio
    async def test_ai_assignment_escapes_executor_name(self, db, monkeypatch):
        """Авто-назначение: имя приходит строкой из ShiftAssignmentService."""
        from uk_management_bot.handlers.shift_management import assignment_a
        from uk_management_bot.services.shift_assignment_service import (
            ShiftAssignmentService,
        )
        from uk_management_bot.services.shift_management_service import (
            ShiftManagementService,
        )

        manager, _ = self._users(db)
        monkeypatch.setattr(assignment_a, "_db_scope", _scope(db))
        monkeypatch.setattr(assignment_a, "get_user_language", lambda *a, **k: "ru")
        monkeypatch.setattr(ShiftManagementService, "list_unassigned_shifts_window",
                            lambda self, *a: [])
        monkeypatch.setattr(
            ShiftAssignmentService, "auto_assign_executors_to_shifts",
            lambda self, shifts, force_reassign=False: {
                "successful_assignments": 1, "failed_assignments": 0,
                "conflicts_found": 1,
                "assignments": [{"executor_name": "Аня & <i>Ко</i>",
                                 "executor_id": 1, "shift_id": 10,
                                 "assignment_score": 0.9}],
                "conflicts": [{"shift_id": 11, "description": "<b>Боб</b> & смена"}],
            })

        cb = _callback("ai_assignment")
        await assignment_a.handle_ai_assignment(
            cb, MagicMock(), db=db, user=manager, roles=["manager"])

        text = _sent_text(cb)
        assert "Аня &amp; &lt;i&gt;Ко&lt;/i&gt;" in text, text
        assert "&lt;b&gt;Боб&lt;/b&gt; &amp; смена" in text, text
        assert "<i>Ко</i>" not in text and "<b>Боб</b>" not in text

    def test_scoring_name_has_no_none(self, db):
        """Сервис отдаёт имя через канон display_name — без «Иван None»."""
        from uk_management_bot.services.shift_assignment_service import (
            ShiftAssignmentService,
        )

        _, executor = self._users(db)
        start = utc_now() + timedelta(days=1)
        shift = Shift(id=12, start_time=start, end_time=start + timedelta(hours=8),
                      status="planned", specialization_focus=["plumbing"])
        db.add(shift)
        db.commit()
        score = ShiftAssignmentService(db).scoring_engine._calculate_executor_score(shift, executor)
        assert score.executor_name == "<b>Ива&н</b>", score.executor_name


# ══════════════════════════════════════════════════════════════════════════
# Комментарии к заявке (services/comment_service + handlers/request_comments)
# ══════════════════════════════════════════════════════════════════════════

class TestComments:
    def _request(self, db, user_id):
        db.add(Request(request_number=NUMBER, user_id=user_id, category="electrics",
                       status="В работе", description="x", urgency="medium",
                       address="a", created_at=datetime.now(timezone.utc),
                       is_returned=False, manager_confirmed=False))

    @pytest.mark.asyncio
    async def test_comment_author_and_text_escaped(self, db):
        from uk_management_bot.database.models.request_comment import RequestComment
        from uk_management_bot.handlers import request_comments

        db.add(User(id=2, telegram_id=APPLICANT_TG, first_name="Жилец & <b>Сын</b>",
                    last_name=None, roles='["applicant"]',
                    active_role="applicant", status="approved"))
        db.flush()
        self._request(db, user_id=2)
        db.flush()
        db.add(RequestComment(request_number=NUMBER, user_id=2,
                              comment_text=EVIL, comment_type="clarification",
                              created_at=datetime.now(timezone.utc)))
        db.commit()

        cb = _callback(f"view_comments_{NUMBER}", APPLICANT_TG)
        await request_comments.handle_view_comments(cb, AsyncMock(), language="ru", _db=db)

        text = _sent_text(cb)
        _assert_escaped(text)
        assert "Жилец &amp; &lt;b&gt;Сын&lt;/b&gt;" in text, text

    @pytest.mark.asyncio
    async def test_comment_confirmation_echo_escaped(self, db):
        from uk_management_bot.handlers import request_comments

        db.add(User(id=2, telegram_id=APPLICANT_TG, first_name="A",
                    roles='["applicant"]', status="approved"))
        db.flush()
        self._request(db, user_id=2)
        db.commit()
        message = MagicMock()
        message.text = EVIL
        message.from_user.id = APPLICANT_TG
        message.answer = AsyncMock()
        state = AsyncMock()
        state.get_data = AsyncMock(return_value={"comment_request_number": NUMBER,
                                                 "comment_type": "clarification"})

        await request_comments.handle_comment_input(message, state, language="ru", _db=db)

        message.answer.assert_awaited()
        text = message.answer.await_args.args[0]
        _assert_escaped(text)


# ══════════════════════════════════════════════════════════════════════════
# Профиль (user_management) и карточка верификации (user_verification)
# ══════════════════════════════════════════════════════════════════════════

def _resident(db):
    db.add(User(id=7, telegram_id=APPLICANT_TG, first_name="Ann & <b>Co</b>",
                last_name="<i>Ltd</i>", username="a<b>", phone="+998 <1>",
                roles='["applicant"]', status="pending",
                verification_notes='примечание <a href="https://evil">x</a>'))
    db.commit()


class TestProfileAndVerification:
    @pytest.mark.asyncio
    async def test_user_management_profile_escaped(self, db):
        from uk_management_bot.handlers.user_management import panels

        _resident(db)
        cb = _callback("view_user_7")
        await panels.handle_view_user_from_notification(
            cb, roles=["manager"], language="ru", _db=db)

        cb.message.answer.assert_awaited()
        text = cb.message.answer.await_args.args[0]
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt; &lt;i&gt;Ltd&lt;/i&gt;" in text, text
        assert "@a&lt;b&gt;" in text, text
        assert "<b>Co</b>" not in text and "<i>Ltd</i>" not in text

    @pytest.mark.asyncio
    async def test_verification_card_escaped(self, db):
        from uk_management_bot.handlers.user_verification import panel

        _resident(db)
        cb = _callback("verification_user_7")
        await panel.show_user_verification(cb, roles=["manager"], language="ru", _db=db)

        text = _sent_text(cb)
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt;" in text, text
        assert "&lt;i&gt;Ltd&lt;/i&gt;" in text and "a&lt;b&gt;" in text, text
        assert "+998 &lt;1&gt;" in text, text
        assert "<a href" not in text and "<b>Co</b>" not in text


# ══════════════════════════════════════════════════════════════════════════
# Карточка здания (address_buildings)
# ══════════════════════════════════════════════════════════════════════════

class TestBuildingCard:
    @pytest.mark.asyncio
    async def test_building_card_escaped(self, db):
        from uk_management_bot.database.models import Building, Yard
        from uk_management_bot.handlers import address_buildings

        yard = Yard(name="Двор <A> & B")
        db.add(yard)
        db.flush()
        building = Building(address="Улица <5> & 7", yard_id=yard.id,
                            description=EVIL)
        db.add(building)
        db.commit()

        cb = _callback(f"addr_building_view:{building.id}")
        await address_buildings.show_building_details(cb, language="ru", _db=db)

        text = _sent_text(cb)
        _assert_escaped(text)
        assert "Улица &lt;5&gt; &amp; 7" in text, text
        assert "Двор &lt;A&gt; &amp; B" in text, text


# ══════════════════════════════════════════════════════════════════════════
# user_management: карточка пользователя (format_user_info) и документы
# ══════════════════════════════════════════════════════════════════════════

class TestUserManagementCards:
    def test_format_user_info_escapes_profile(self, db):
        """Рендер карточки (listing/fsm/actions/roles_specs) — текст уходит с
        parse_mode=HTML."""
        from uk_management_bot.services.user_management_service import (
            UserManagementService,
        )

        _resident(db)
        user = db.get(User, 7)
        svc = UserManagementService(db)
        detailed = svc.format_user_info(user, "ru", detailed=True)
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt; &lt;i&gt;Ltd&lt;/i&gt;" in detailed, detailed
        assert "@a&lt;b&gt;" in detailed and "+998 &lt;1&gt;" in detailed, detailed
        assert "<b>Co</b>" not in detailed and "<i>Ltd</i>" not in detailed
        brief = svc.format_user_info(user, "ru", detailed=False)
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt;" in brief, brief

    @pytest.mark.asyncio
    async def test_documents_view_escapes_name_file_and_notes(self, db):
        from uk_management_bot.database.models.user_verification import (
            DocumentType, UserDocument,
        )
        from uk_management_bot.handlers.user_management import actions

        _resident(db)
        db.add(UserDocument(user_id=7, document_type=DocumentType.PASSPORT,
                            file_id="f1", file_name="скан <1> & 2.jpg",
                            verification_notes=EVIL))
        db.commit()

        cb = _callback("user_action_view_documents_7")
        await actions.handle_view_user_documents(
            cb, roles=["manager"], active_role="manager", user=None,
            language="ru", _db=db)

        text = _sent_text(cb)
        _assert_escaped(text)
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt;" in text, text
        assert "скан &lt;1&gt; &amp; 2.jpg" in text, text


# ══════════════════════════════════════════════════════════════════════════
# Дворы пользователя: ровно один слой экранирования
# ══════════════════════════════════════════════════════════════════════════

class TestUserYardsSingleEscape:
    @pytest.mark.asyncio
    async def test_name_escaped_exactly_once(self, db, monkeypatch):
        from uk_management_bot.handlers import user_yards_management as uym

        _resident(db)
        # Клавиатура сама открывает session_scope — к тексту отношения не имеет.
        monkeypatch.setattr(uym, "get_user_yards_keyboard", lambda *a, **k: None)
        cb = _callback(f"manage_user_yards_{APPLICANT_TG}")
        await uym.handle_manage_user_yards(cb, roles=["manager"], user=None, _db=db)

        text = _sent_text(cb)
        assert "Ann &amp; &lt;b&gt;Co&lt;/b&gt;" in text, text
        assert "&amp;amp;" not in text and "&amp;lt;" not in text, "двойное экранирование"


# ══════════════════════════════════════════════════════════════════════════
# Госномер авто (access_control): ввод жителя в HTML-списках
# ══════════════════════════════════════════════════════════════════════════

class TestVehiclePlates:
    def test_rendered_lists_escape_plate(self):
        from uk_management_bot.handlers import access_control as ac

        plate = 'A<1>&"B'
        vehicles = ac._render_vehicles(
            [{"plate_number_normalized": plate, "make": "Lada <x>", "color": "&", "status": "active"}], "ru")
        requests = ac._render_requests([{"plate_number_normalized": plate, "status": "pending"}], "ru")
        passes = ac._render_passes(
            [{"plate_number_normalized": plate, "status": "active", "pass_type": "guest",
              "valid_until": None}], "ru")
        for text in (vehicles, requests, passes):
            assert "A&lt;1&gt;&amp;&quot;B" in text, text
            assert "<1>" not in text, text
        assert "Lada &lt;x&gt; &amp;" in vehicles, vehicles


class TestDocumentRequestMessages:
    """Бот собран build_bot(html=True): send_to_user без parse_mode = HTML."""

    def test_single_and_multiple_requests_escape_admin_text(self):
        from uk_management_bot.services.notification_service.documents import (
            build_document_request_message,
            build_multiple_documents_request_message,
        )

        user = SimpleNamespace(telegram_id=1, language="ru")
        texts = [
            build_document_request_message(user, EVIL, "passport"),
            build_document_request_message(user, EVIL, "passport", for_channel=True),
            build_multiple_documents_request_message(user, EVIL, ["passport"]),
            build_multiple_documents_request_message(user, EVIL, ["passport"], for_channel=True),
        ]
        for text in texts:
            _assert_escaped(text)


def test_channel_status_message_escapes_legacy_category():
    """A9-P2-2: сырая category из легаси-строки не ломает HTML сообщения канала."""
    from types import SimpleNamespace

    from uk_management_bot.services.notification_service.requests_roles import (
        _build_request_status_message_channel,
    )

    request = SimpleNamespace(request_number="260923-001", category='<a href="https://evil">x</a> & y')
    text = _build_request_status_message_channel(request, "Новая", "В работе")
    assert "<a href" not in text
    assert "&lt;a href=&quot;https://evil&quot;&gt;x&lt;/a&gt; &amp; y" in text
