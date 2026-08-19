"""Переназначение исполнителя из бота: канон, гонка old-notice, права, роутинг.

Ключевые свойства, которые здесь пинятся (каждое — RED-первым против HEAD):

1. Снятый исполнитель берётся из `outcome.old_state`, а НЕ из преflight'а.
   Между фазами другой менеджер успевает подменить исполнителя, и уведомление
   «вас сняли» ушло бы не тому, кого сняли на самом деле.
2. Уведомления собираются на СВЕЖЕЙ сессии после коммита команды — иначе
   identity map отдаёт stale-заявку и адресатом «вам назначена» становится
   снятый исполнитель.
3. `resolve_ctx` пиннит ВЛАДЕНИЕ префиксом. Он НЕ проверяет права: у
   `admin_router` нет root-гейта, житель тоже разрешится в admin-хендлер и
   получит отказ уже в теле. Отказ проверяется прямым вызовом хендлера.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.admin import reassignment as mod
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
)

NUMBER = "260819-001"
APPLICANT_ID, OLD_ID, NEW_ID, THIRD_ID, MANAGER_ID = 1, 2, 3, 4, 5


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _user(db, uid, tg, *, roles='["executor"]', language="ru", status="approved",
          specialization="electrician", first_name="U"):
    user = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name=first_name,
                roles=roles, status=status, language=language,
                specialization=specialization)
    db.add(user)
    db.commit()
    return user


def _request(db, *, executor_id=None, status=REQUEST_STATUS_NEW,
             category="Электрика"):
    req = Request(request_number=NUMBER, user_id=APPLICANT_ID,
                  executor_id=executor_id, category=category,
                  description="Не горит лампа", address="Дом 1", status=status)
    db.add(req)
    db.commit()
    return req


def _assignment(db, *, kind="individual", executor_id=None, group=None):
    row = RequestAssignment(request_number=NUMBER, assignment_type=kind,
                            executor_id=executor_id, group_specialization=group,
                            created_by=MANAGER_ID, status="active")
    db.add(row)
    db.commit()
    return row


def _outcome(*, old_executor_id, intents=()):
    """CommandOutcome-двойник: важен только снимок ДО и набор интентов."""
    return SimpleNamespace(
        request_number=NUMBER,
        no_op=False,
        old_state=SimpleNamespace(request_number=NUMBER, user_id=APPLICANT_ID,
                                  status=REQUEST_STATUS_IN_PROGRESS,
                                  executor_id=old_executor_id),
        post_commit_intents=tuple(intents),
    )


def _intent(kind, data=None):
    return SimpleNamespace(kind=kind, data=data or {})


# ══════════════════════════════════════════════════════════════════════════
# Фаза 3: снятый берётся из outcome.old_state (гонка между фазами)
# ══════════════════════════════════════════════════════════════════════════


class TestAftermathUsesOutcome:
    def test_old_notice_goes_to_whoever_the_command_actually_replaced(self, db):
        """Гонка: преflight видел OLD, но команда под FOR UPDATE сняла THIRD.

        Если получателя запомнить в фазе 1, «вас сняли» уедет OLD — человеку,
        которого уже никто не снимал.
        """
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200)
        _user(db, THIRD_ID, 400, language="uz")
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        after = mod._aftermath(db, NUMBER, _outcome(old_executor_id=THIRD_ID), "ru")

        assert after.old_notice is not None
        assert after.old_notice[0] == 400, "уведомлён должен быть фактически снятый"

    def test_old_notice_is_rendered_in_recipient_language(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200, language="uz")
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        from uk_management_bot.utils.helpers import get_text

        after = mod._aftermath(db, NUMBER, _outcome(old_executor_id=OLD_ID), "ru")
        expected = get_text("notifications.workflow.reassigned_away",
                            language="uz", request_number=NUMBER)
        assert after.old_notice[1] == expected

    def test_no_old_notice_when_executor_did_not_change(self, db):
        """old == new: снимать было некого, «вас сняли» было бы ложью."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        after = mod._aftermath(db, NUMBER, _outcome(old_executor_id=NEW_ID), "ru")
        assert after.old_notice is None

    def test_no_old_notice_for_group_assignment(self, db):
        """Групповое назначение — индивидуального исполнителя не было."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)
        _assignment(db, kind="group", group="electrician")

        after = mod._aftermath(db, NUMBER, _outcome(old_executor_id=None), "ru")
        assert after.old_notice is None
        assert after.old_label, "подпись «откуда» обязана быть непустой"

    def test_old_label_falls_back_to_unassigned(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        from uk_management_bot.utils.helpers import get_text

        after = mod._aftermath(db, NUMBER, _outcome(old_executor_id=None), "ru")
        assert after.old_label == get_text(
            "admin.handlers.reassign_from_unassigned", language="ru")

    def test_notify_messages_target_the_new_executor(self, db):
        """Сбор на свежей сессии: адресат наряда — НОВЫЙ исполнитель."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200)
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        from uk_management_bot.utils.request_workflow import Action

        outcome = _outcome(
            old_executor_id=OLD_ID,
            intents=[_intent("notify", {"action": Action.MANAGER_ASSIGN.value})])
        after = mod._aftermath(db, NUMBER, outcome, "ru")

        targets = {tg for tg, _ in after.messages}
        assert 300 in targets, "новый исполнитель обязан получить наряд"
        assert 200 not in targets, "снятый не должен получить «вам назначена»"
        assert 100 in targets, "житель получает уведомление о назначении"


# ══════════════════════════════════════════════════════════════════════════
# Фаза 1: преflight
# ══════════════════════════════════════════════════════════════════════════


class TestPreflight:
    def test_same_executor_is_an_honest_refusal(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        assert mod._preflight(db, NUMBER, NEW_ID, "ru").verdict == "same_executor"

    def test_bad_status_is_refused(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_PURCHASE)

        assert mod._preflight(db, NUMBER, NEW_ID, "ru").verdict == "bad_status"

    def test_missing_request_is_refused(self, db):
        assert mod._preflight(db, NUMBER, NEW_ID, "ru").verdict == "request_not_found"

    def test_non_executor_target_is_refused(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300, roles='["applicant"]')
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        assert mod._preflight(db, NUMBER, NEW_ID, "ru").verdict == "executor_not_found"

    def test_unapproved_target_is_refused(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300, status="pending")
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        assert mod._preflight(db, NUMBER, NEW_ID, "ru").verdict == "executor_not_found"


# ══════════════════════════════════════════════════════════════════════════
# Кандидаты
# ══════════════════════════════════════════════════════════════════════════


class TestCandidates:
    def test_current_executor_is_excluded(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200)
        _user(db, NEW_ID, 300)
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        _, candidates = mod._candidates(db, NUMBER, "ru")
        ids = {c.id for c in candidates}
        assert OLD_ID not in ids
        assert NEW_ID in ids

    def test_wrong_specialization_is_excluded(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200)
        _user(db, NEW_ID, 300, specialization="plumber")
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        _, candidates = mod._candidates(db, NUMBER, "ru")
        assert NEW_ID not in {c.id for c in candidates}

    def test_universal_joker_is_accepted(self, db):
        """BUG-166: подбор общим предикатом, джокер `universal` подходит всем."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, OLD_ID, 200)
        _user(db, NEW_ID, 300, specialization="universal")
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        _, candidates = mod._candidates(db, NUMBER, "ru")
        assert NEW_ID in {c.id for c in candidates}

    def test_candidates_are_dto_not_orm(self, db):
        """ORM не выходит за границу run_db: за ней нет живой сессии."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        _, candidates = mod._candidates(db, NUMBER, "ru")
        assert all(isinstance(c, mod.Candidate) for c in candidates)


# ══════════════════════════════════════════════════════════════════════════
# Дежурный
# ══════════════════════════════════════════════════════════════════════════


class TestDuty:
    def test_current_executor_is_excluded_from_duty_pick(self, db, monkeypatch):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        seen = {}
        import uk_management_bot.services.dispatch as dispatch

        def _spy(spec, db=None, exclude_user_ids=frozenset(), strict=False):
            seen["exclude"] = exclude_user_ids
            seen["strict"] = strict
            return None

        monkeypatch.setattr(dispatch, "pick_duty_executor_id", _spy)
        mod._resolve_duty(db, NUMBER, "ru")

        assert seen["exclude"] == frozenset({OLD_ID})
        assert seen["strict"] is True, "интерактивный вызов не смеет маскировать аварию БД"

    def test_no_duty_verdict_when_nobody_found(self, db, monkeypatch):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        import uk_management_bot.services.dispatch as dispatch
        monkeypatch.setattr(dispatch, "pick_duty_executor_id",
                            lambda *a, **kw: None)

        assert mod._resolve_duty(db, NUMBER, "ru").verdict == "no_duty"

    def test_lookup_failure_is_not_reported_as_no_duty(self, db, monkeypatch):
        """Авария подбора ≠ «нет дежурного»: тексты разные, действия тоже."""
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _request(db, executor_id=OLD_ID, status=REQUEST_STATUS_IN_PROGRESS)

        import uk_management_bot.services.dispatch as dispatch

        def _boom(*a, **kw):
            raise RuntimeError("БД недоступна")

        monkeypatch.setattr(dispatch, "pick_duty_executor_id", _boom)

        assert mod._resolve_duty(db, NUMBER, "ru").verdict == "duty_lookup_failed"


# ══════════════════════════════════════════════════════════════════════════
# Права: resolve_ctx пиннит владение, отказ проверяется прямым вызовом
# ══════════════════════════════════════════════════════════════════════════


def _callback(data):
    cb = MagicMock()
    cb.data = data
    cb.id = "cb1"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_applicant_is_refused_before_touching_db(self):
        cb = _callback(f"{mod.MENU_PREFIX}{NUMBER}")

        with patch.object(mod, "run_db", new=AsyncMock()) as run_db:
            await mod.handle_reassign_menu(cb, roles=["applicant"],
                                           user=MagicMock(), language="ru")

        cb.answer.assert_awaited()
        run_db.assert_not_awaited(), "до БД доходить не должно"

    @pytest.mark.asyncio
    async def test_admin_without_manager_role_is_refused(self):
        """`has_admin_access` пропускает admin, а канон требует manager —
        без второй проверки админ дошёл бы до команды и получил NotAuthorized
        в виде общей ошибки."""
        from uk_management_bot.utils.helpers import get_text

        cb = _callback(f"{mod.MENU_PREFIX}{NUMBER}")
        with patch.object(mod, "run_db", new=AsyncMock()):
            await mod.handle_reassign_menu(cb, roles=["admin"],
                                           user=MagicMock(), language="ru")

        cb.answer.assert_awaited_with(
            get_text("admin.handlers.reassign_manager_only", language="ru"),
            show_alert=True)

    @pytest.mark.asyncio
    async def test_executor_is_refused(self):
        cb = _callback(f"{mod.DUTY_PREFIX}{NUMBER}")

        with patch.object(mod, "run_db", new=AsyncMock()) as run_db:
            await mod.handle_reassign_duty(cb, roles=["executor"],
                                           user=MagicMock(), language="ru")

        cb.answer.assert_awaited()
        run_db.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════
# Роутинг: владение префиксами
# ══════════════════════════════════════════════════════════════════════════


class TestRouting:
    def _resolve(self, data, ctx):
        from uk_management_bot.tests.handlers.routing_probe import (
            make_callback, resolve_ctx,
        )
        from uk_management_bot.tests.handlers.test_dead_handlers_retired import ROUTERS

        return resolve_ctx(ROUTERS, make_callback(data), "callback_query", **ctx)

    MANAGER = {"roles": ["manager"], "user": None}
    APPLICANT = {"roles": ["applicant"], "user": None}

    @pytest.mark.parametrize("prefix,handler", [
        ("req_reassign_menu_", "handle_reassign_menu"),
        ("req_reassign_duty_", "handle_reassign_duty"),
        ("req_reassign_pick_", "handle_reassign_pick"),
    ])
    def test_manager_reaches_our_handlers(self, prefix, handler):
        module, name = self._resolve(f"{prefix}{NUMBER}", self.MANAGER)
        assert name == handler
        assert module.endswith("admin.reassignment")

    def test_commit_entry_is_owned(self):
        module, name = self._resolve(f"req_reassign_to_{NUMBER}_7", self.MANAGER)
        assert name == "handle_reassign_to"

    def test_commit_entry_rejects_non_canonical_payload(self):
        """Строгий регекс: открытый префикс — источник BUG-179."""
        for bad in (f"req_reassign_to_{NUMBER}", "req_reassign_to_abc_1",
                    f"req_reassign_to_{NUMBER}_7_9"):
            assert self._resolve(bad, self.MANAGER) != (
                "uk_management_bot.handlers.admin.reassignment", "handle_reassign_to"), bad

    def test_applicant_also_resolves_to_admin_handler(self):
        """У admin_router нет root-гейта: житель ДОХОДИТ до хендлера и получает
        отказ в теле. Ожидание «не доходит» было бы ложным пином."""
        resolved = self._resolve(f"{mod.MENU_PREFIX}{NUMBER}", self.APPLICANT)
        assert resolved is not None
        assert resolved[1] == "handle_reassign_menu"


# ══════════════════════════════════════════════════════════════════════════
# Клавиатуры
# ══════════════════════════════════════════════════════════════════════════


class TestKeyboards:
    def _texts(self, markup):
        return [b.text for row in markup.inline_keyboard for b in row]

    def _callbacks(self, markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    def test_reassign_row_shown_for_individual_assignment(self):
        from uk_management_bot.keyboards.admin import get_reassign_button_row

        row = get_reassign_button_row(NUMBER, assignment_type="individual",
                                      status=REQUEST_STATUS_IN_PROGRESS,
                                      roles=["manager"])
        assert row and row[0].callback_data == f"req_reassign_menu_{NUMBER}"

    def test_group_assignment_gets_assign_label_not_reassign(self):
        from uk_management_bot.keyboards.admin import get_reassign_button_row
        from uk_management_bot.utils.helpers import get_text

        row = get_reassign_button_row(NUMBER, assignment_type="group",
                                      status=REQUEST_STATUS_NEW, roles=["manager"])
        assert row[0].text == get_text(
            "admin.keyboards.assign_executor_to_request", language="ru")

    @pytest.mark.parametrize("kwargs", [
        {"assignment_type": None, "status": REQUEST_STATUS_NEW, "roles": ["manager"]},
        {"assignment_type": "individual", "status": REQUEST_STATUS_PURCHASE,
         "roles": ["manager"]},
        {"assignment_type": "individual", "status": REQUEST_STATUS_NEW,
         "roles": ["admin"]},
        {"assignment_type": "individual", "status": REQUEST_STATUS_NEW, "roles": []},
    ])
    def test_reassign_row_hidden(self, kwargs):
        from uk_management_bot.keyboards.admin import get_reassign_button_row

        assert get_reassign_button_row(NUMBER, **kwargs) == []

    def test_picker_back_button_returns_to_reassign_menu(self):
        from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard

        markup = get_executors_by_category_keyboard(
            NUMBER, "", [mod.Candidate(id=9, first_name="A", last_name=None,
                                       username="a")],
            callback_prefix=mod.TO_PREFIX,
            back_callback_data=f"{mod.MENU_PREFIX}{NUMBER}")

        callbacks = self._callbacks(markup)
        assert f"req_reassign_to_{NUMBER}_9" in callbacks
        assert f"{mod.MENU_PREFIX}{NUMBER}" in callbacks
        assert f"back_to_assignment_type_{NUMBER}" not in callbacks

    def test_picker_defaults_preserve_primary_assign_flow(self):
        from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard

        markup = get_executors_by_category_keyboard(
            NUMBER, "", [mod.Candidate(id=9, first_name="A", last_name=None,
                                       username="a")])
        callbacks = self._callbacks(markup)
        assert f"assign_executor_{NUMBER}_9" in callbacks
        assert f"back_to_assignment_type_{NUMBER}" in callbacks

    def test_picker_honours_language(self):
        """Живой колл-сайт терял lang — picker всегда рисовался по-русски."""
        from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
        from uk_management_bot.utils.helpers import get_text

        markup = get_executors_by_category_keyboard(NUMBER, "", [], language="uz")
        assert get_text("admin.keyboards.no_available_executors",
                        language="uz") in self._texts(markup)


# ══════════════════════════════════════════════════════════════════════════
# Realtime: ручной request.updated только когда канон интент не выпустил
# ══════════════════════════════════════════════════════════════════════════


class TestRealtime:
    @pytest.mark.asyncio
    async def test_manual_publish_when_public_status_did_not_change(self):
        cb = _callback("x")
        after = mod.Aftermath(messages=[], old_notice=None, old_label="A",
                              new_executor_name="B")
        outcome = _outcome(old_executor_id=OLD_ID, intents=[_intent("notify")])

        with patch("uk_management_bot.services.redis_pubsub.publish_request_event",
                   new=AsyncMock()) as publish, \
             patch("uk_management_bot.services.workflow_notifications."
                   "send_notify_messages", new=AsyncMock()):
            await mod._deliver(cb, NUMBER, outcome, after, "ru")

        publish.assert_awaited_once_with("request.updated", {"number": NUMBER})

    @pytest.mark.asyncio
    async def test_no_duplicate_publish_when_canon_already_emitted_realtime(self):
        cb = _callback("x")
        after = mod.Aftermath(messages=[], old_notice=None, old_label="A",
                              new_executor_name="B")
        outcome = _outcome(old_executor_id=None,
                           intents=[_intent("notify"), _intent("realtime")])

        with patch("uk_management_bot.services.redis_pubsub.publish_request_event",
                   new=AsyncMock()) as publish, \
             patch("uk_management_bot.services.workflow_notifications."
                   "send_notify_messages", new=AsyncMock()):
            await mod._deliver(cb, NUMBER, outcome, after, "ru")

        publish.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════
# Команда: аргументы канона и отказ без команды
# ══════════════════════════════════════════════════════════════════════════


class TestCommand:
    @pytest.mark.asyncio
    async def test_manager_assign_is_called_with_new_executor_and_manager_actor(self):
        from uk_management_bot.utils.request_workflow import Action

        cb = _callback(f"req_reassign_to_{NUMBER}_{NEW_ID}")
        pre = mod.Preflight("ok", request_number=NUMBER, new_executor_id=NEW_ID)
        captured = {}

        def _fake_run(factory, number, principal, command, **kw):
            captured.update(number=number, principal=principal, command=command)
            return _outcome(old_executor_id=OLD_ID)

        with patch("uk_management_bot.services.workflow_runner.run_command_sync",
                   side_effect=_fake_run), \
             patch.object(mod, "run_db", new=AsyncMock(
                 return_value=mod.Aftermath())), \
             patch.object(mod, "_deliver", new=AsyncMock()):
            await mod._commit_reassign(cb, SimpleNamespace(id=MANAGER_ID), "ru", pre)

        assert captured["command"].action is Action.MANAGER_ASSIGN
        assert captured["command"].payload == {"executor_id": NEW_ID}
        assert captured["principal"].kind == "user"
        assert captured["principal"].user_id == MANAGER_ID

    @pytest.mark.asyncio
    async def test_same_executor_does_not_reach_the_command(self, db):
        _user(db, APPLICANT_ID, 100, roles='["applicant"]')
        _user(db, NEW_ID, 300)
        _request(db, executor_id=NEW_ID, status=REQUEST_STATUS_IN_PROGRESS)

        cb = _callback(f"req_reassign_to_{NUMBER}_{NEW_ID}")

        with patch("uk_management_bot.services.workflow_runner.run_command_sync") as run, \
             patch.object(mod, "run_db", new=AsyncMock(
                 side_effect=lambda unit, db=None: unit(db))):
            await mod.handle_reassign_to(cb, roles=["manager"],
                                         user=SimpleNamespace(id=MANAGER_ID),
                                         language="ru")

        run.assert_not_called()
