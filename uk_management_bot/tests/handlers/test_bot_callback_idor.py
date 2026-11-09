"""IDOR-матрица callback-хендлеров бота (ревью 2026-11-07,
docs/audit/auth-connectors-review-2026-11-07.md, часть A).

Каждый callback, где из `callback_data` берётся id объекта и который не закрыт
staff-гейтом, должен быть в `BOT_IDOR_COVERAGE` с категорией и ссылкой на тест.
Поведенческие пары «чужой → отказ без изменений и без утечки / свой → успех»
для мест, где их не было, — ниже, на настоящем sqlite.
"""
from __future__ import annotations

import inspect
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.utils.media_helpers as media_helpers
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers import request_acceptance, request_comments, request_reports
from uk_management_bot.handlers.requests import executor as ex
from uk_management_bot.handlers.requests import listing, myrequests
from uk_management_bot.services.request_handler_service import guard_executor_issue

OWNER_TG, OTHER_TG, EXEC_TG, STRANGER_EXEC_TG = 9101, 9102, 9111, 9112
RN = "261107-101"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    @contextmanager
    def scope(_):
        yield session

    for module in (ex, listing, myrequests):
        monkeypatch.setattr(module, "_db_scope", scope)
    yield session
    session.close()


@pytest.fixture
def world(db):
    def user(tg, roles):
        return User(telegram_id=tg, first_name=f"U{tg}", roles=roles,
                    active_role=roles.split('"')[1], status="approved", language="ru")

    owner, other = user(OWNER_TG, '["applicant"]'), user(OTHER_TG, '["applicant"]')
    executor, stranger = user(EXEC_TG, '["executor"]'), user(STRANGER_EXEC_TG, '["executor"]')
    db.add_all([owner, other, executor, stranger])
    db.flush()
    db.add(Request(request_number=RN, user_id=owner.id, category="plumbing",
                   description="течёт", status="Исполнено", urgency="low",
                   executor_id=executor.id, notes="секрет диалога",
                   completion_report="отчёт исполнителя"))
    db.commit()
    return {"owner": owner, "other": other, "executor": executor, "stranger": stranger}


def _callback(data: str, tg: int):
    cb = MagicMock()
    cb.data = data
    cb.id = "cb-1"
    cb.from_user.id = tg
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _state(data: dict | None = None):
    st = MagicMock()
    st.get_data = AsyncMock(return_value=data or {})
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _sent_texts(cb) -> str:
    calls = (cb.answer.await_args_list + cb.message.answer.await_args_list
             + cb.message.edit_text.await_args_list)
    return " ".join(str(c.args[0]) for c in calls if c.args)


# ── BOT-01: фотоотчёт исполнителя через бот ─────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("who,allowed", [("other", False), ("stranger", False), ("executor", True)])
async def test_finish_completion_uploads_only_for_assigned(world, db, monkeypatch, who, allowed):
    """Медиа уходит в media-service как completion_* заявки из callback —
    только после проверки права; чужой не подкладывает «фотоотчёт исполнителя»."""
    db.query(Request).filter_by(request_number=RN).update({"status": "В работе"})
    db.commit()
    upload = AsyncMock(return_value=None)
    monkeypatch.setattr(media_helpers, "upload_report_file_to_media_service", upload)
    runner = MagicMock(return_value=(None, "requests.request_not_found"))
    monkeypatch.setattr(ex, "_run_executor_command", runner)
    cb = _callback(f"executor_finish_completion_{RN}", world[who].telegram_id)
    state = _state({"completion_comment": "ок", "completion_media": [{"type": "photo", "file_id": "F1"}]})

    await ex.executor_finish_completion(cb, state)

    assert upload.await_count == (1 if allowed else 0)
    assert runner.called is allowed


# ── BOT-02: оракул статуса в списании материалов ────────────────────────


@pytest.mark.parametrize("status", ["Новая", "В работе"])
def test_material_guard_does_not_disclose_foreign_status(world, db, status):
    db.query(Request).filter_by(request_number=RN).update({"status": status})
    db.commit()
    _, _, err = guard_executor_issue(db, request_number=RN, telegram_id=STRANGER_EXEC_TG)
    assert err == "materials.issue.not_executor"


def test_material_guard_lets_assigned_executor_in(world, db):
    db.query(Request).filter_by(request_number=RN).update({"status": "В работе"})
    db.commit()
    assert guard_executor_issue(db, request_number=RN, telegram_id=EXEC_TG)[2] is None


# ── Просмотры: юниты загрузки отказывают чужому ────────────────────────


@pytest.mark.parametrize("tg,verdict", [(OTHER_TG, "forbidden"), (STRANGER_EXEC_TG, "forbidden"), (OWNER_TG, "ok")])
def test_completed_view(world, db, tg, verdict):
    assert request_acceptance._load_completed_view(db, tg, RN)[1] == verdict


@pytest.mark.parametrize("tg,verdict", [(OTHER_TG, "no_access"), (STRANGER_EXEC_TG, "no_access"), (OWNER_TG, "ok")])
def test_report_view(world, db, tg, verdict):
    assert request_reports._load_report_view(db, RN, tg, "ru")[0] == verdict


@pytest.mark.parametrize("tg,ok", [(OTHER_TG, False), (STRANGER_EXEC_TG, False), (OWNER_TG, True), (EXEC_TG, True)])
def test_comments_view(world, db, tg, ok):
    verdict = request_comments._load_all_comments_view(db, RN, tg, "ru")[0]
    assert (verdict != "no_access") is ok


# ── Правка и ответ на уточнение ─────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("tg,allowed", [(OTHER_TG, False), (OWNER_TG, True)])
async def test_edit_request_entry(world, tg, allowed):
    cb, state = _callback(f"edit_{RN}", tg), _state()
    await listing.handle_edit_request(cb, state)
    assert state.set_state.await_count == (1 if allowed else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("tg,allowed", [(OTHER_TG, False), (OWNER_TG, True)])
async def test_reply_clarify_does_not_leak_or_write_foreign(world, db, tg, allowed):
    cb = _callback(f"replyclarify_{RN}", tg)
    await myrequests.handle_reply_clarify_start(cb, _state())
    assert ("секрет диалога" in _sent_texts(cb)) is allowed

    msg = MagicMock()
    msg.from_user.id = tg
    msg.text = "ответ"
    msg.answer = AsyncMock()
    monkey_kb = AsyncMock(return_value=None)
    myrequests.get_user_contextual_keyboard, saved = monkey_kb, myrequests.get_user_contextual_keyboard
    try:
        await myrequests.handle_reply_clarify_text(msg, _state({"reply_request_number": RN}))
    finally:
        myrequests.get_user_contextual_keyboard = saved
    db.expire_all()
    notes = db.query(Request).filter_by(request_number=RN).one().notes
    assert ("ответ" in notes) is allowed


# ══════════════════════════ Реестр и ратчет ═══════════════════════════════

#: Колбэки с id из callback_data, не закрытые staff-гейтом (root ActionGate /
#: @require_action со staff-ролями / ранний отказ `if not has_admin_access…`).
#: Ключ — (файл относительно handlers/, функция). Категории:
#:   NO-OBJECT  — в callback не объект (страница, фильтр, ключ категории/срочности/языка);
#:   SELF       — данные/действие только от from_user (выборка по telegram_id);
#:   OWNER      — владение проверяется в юните/сервисе (фильтр или сравнение);
#:   ACCESS     — канон has_request_access_sync / can_*_sync;
#:   CANON      — мутация через run_command (авторизует владельца/исполнителя сам);
#:   ENTRY      — вход FSM без чтения объекта и побочных эффектов, финал авторизован;
#:   BY-DESIGN  — решение владельца (ссылка).
BOT_IDOR_COVERAGE: dict[tuple[str, str], str] = {
    ("executor_done.py", "close_with_photo"): "OWNER: личный чат + executor_by_telegram + complete_with_photo (not_assigned); test_executor_done_callback::test_foreign_presser_is_refused",
    ("profile_editing.py", "handle_language_choice"): "NO-OBJECT (код языка, свой профиль)",
    ("inspector_requests.py", "inspector_yard_page"): "NO-OBJECT (страница)",
    ("inspector_requests.py", "inspector_yard_selected"): "BY-DESIGN: обходчик — любой активный двор/дом (requests.create_inspection)",
    ("inspector_requests.py", "inspector_building_page"): "NO-OBJECT (страница)",
    ("inspector_requests.py", "inspector_building_selected"): "BY-DESIGN: обходчик — любой активный дом; resolve_request_address(inspector)",
    ("inspector_requests.py", "inspector_category_selected"): "NO-OBJECT (ключ категории)",
    ("inspector_requests.py", "inspector_urgency_selected"): "NO-OBJECT (срочность)",
    ("requests/create.py", "handle_address_selection"): "OWNER: resolve_request_address(applicant) — свои двор/дом/квартира; tests/api/test_inspector_requests.py::test_resolver_foreign_apartment_403",
    ("requests/create.py", "handle_address_page"): "SELF (свои адреса; номер страницы)",
    ("requests/create_callbacks.py", "handle_category_selection"): "SELF (свои адреса; ключ категории)",
    ("requests/create_callbacks.py", "handle_urgency_selection"): "NO-OBJECT (срочность)",
    ("requests/create_callbacks.py", "handle_confirmation"): "NO-OBJECT (да/нет; данные из своего FSM)",
    ("requests/listing.py", "handle_pagination"): "SELF (свои заявки; страница)",
    ("requests/listing.py", "handle_view_request"): "ACCESS: has_request_access_sync; test_handler_permissions",
    ("requests/listing.py", "handle_back_to_list"): "SELF (свои заявки; страница)",
    ("requests/listing.py", "handle_cancel_request"): "CANON: RequestService.update_status_by_actor → run_command_sync (NotAuthorized)",
    ("requests/listing.py", "handle_edit_request"): "OWNER: request.user_id == user.id; test_edit_request_entry",
    ("requests/listing.py", "handle_approve_request"): "ENTRY: только клавиатура оценки; приёмка — save_rating → APPLICANT_ACCEPT",
    ("requests/myrequests.py", "handle_reply_clarify_start"): "OWNER: диалог только владельцу, запись перепроверяет; test_reply_clarify_does_not_leak_or_write_foreign",
    ("requests/myrequests.py", "handle_status_filter"): "SELF (фильтр своих заявок)",
    ("requests/myrequests.py", "handle_category_filter"): "SELF (фильтр своих заявок)",
    ("requests/myrequests.py", "handle_period_filter"): "SELF (фильтр своих заявок)",
    ("requests/myrequests.py", "handle_executor_filter"): "SELF (фильтр своих заявок)",
    ("requests/executor.py", "executor_view_media"): "ACCESS: has_request_access_sync; test_executor_media_access::test_foreign_user_gets_not_found_and_no_media",
    ("requests/executor.py", "claim_group_request"): "CANON: EXECUTOR_CLAIM (смена + группа + unclaimed)",
    ("requests/executor.py", "executor_request_purchase"): "ENTRY: финал — run_command (назначение + смена)",
    ("requests/executor.py", "executor_complete_request"): "ENTRY: финал — executor_finish_completion",
    ("requests/executor.py", "executor_finish_completion"): "ACCESS: can_upload_completion_sync ДО загрузки в media (BOT-01); test_finish_completion_uploads_only_for_assigned",
    ("requests/executor.py", "executor_return_to_work"): "CANON: run_command (исполнитель заявки)",
    ("requests/executor_before.py", "executor_before_start"): "ACCESS: check_before_access; test_executor_before.py",
    ("requests/executor_before.py", "executor_before_done"): "ACCESS: check_before_access до скачивания; test_executor_before.py",
    ("requests/materials.py", "start_material_issue"): "OWNER: guard_executor_issue (executor_id); test_material_issue_handlers::test_start_rejects_stranger_executor, test_material_guard_does_not_disclose_foreign_status",
    ("requests/materials.py", "paginate_materials"): "NO-OBJECT (страница справочника)",
    ("requests/materials.py", "pick_material"): "OWNER: confirm перепроверяет guard; test_material_issue_handlers::test_confirm_recheck_guards_after_status_change",
    ("admin/views.py", "handle_return_to_work_cancel"): "NO-OBJECT (сброс своего FSM, БД не читается)",
    ("request_acceptance.py", "view_completed_request"): "OWNER: _load_completed_view → forbidden; test_completed_view",
    ("request_acceptance.py", "view_completion_media"): "OWNER: _load_completion_media → forbidden",
    ("request_acceptance.py", "accept_request"): "ENTRY: только клавиатура оценки",
    ("request_acceptance.py", "save_rating"): "CANON: APPLICANT_ACCEPT (owner|сосед)",
    ("request_acceptance.py", "return_request"): "ENTRY: финал — process_return_request → APPLICANT_RETURN (только owner)",
    ("my_shifts/viewing.py", "handle_shift_details"): "OWNER: execution.work + Shift.user_id; test_aud337_my_shifts_offload",
    ("elevators/menu.py", "handle_yard"): "BY-DESIGN A10-INT-10 (elevators.technician: реестр целиком)",
    ("elevators/menu.py", "handle_building"): "BY-DESIGN A10-INT-10",
    ("elevators/card.py", "handle_card"): "BY-DESIGN A10-INT-10",
    ("elevators/status.py", "handle_status_menu"): "BY-DESIGN A10-INT-10",
    ("elevators/status.py", "handle_status_pick"): "BY-DESIGN A10-INT-10",
    ("elevators/repair.py", "handle_repair_start"): "BY-DESIGN A10-INT-10",
    ("elevators/repair.py", "handle_urgency"): "BY-DESIGN A10-INT-10",
    ("elevators/repair.py", "handle_repair_status_offer"): "BY-DESIGN A10-INT-10; test_elevators_repair::test_repair_status_offer_foreign_number_rejected",
    ("elevators/maintenance.py", "handle_occurrences"): "BY-DESIGN A10-INT-10",
    ("elevators/maintenance.py", "handle_occurrence_pick"): "BY-DESIGN A10-INT-10",
    ("shift_transfer.py", "handle_shift_selection"): "OWNER: фильтр Shift.user_id в SQL (_check_shift_selectable)",
    ("shift_transfer.py", "handle_reason_selection"): "NO-OBJECT (причина)",
    ("shift_transfer.py", "handle_urgency_selection"): "NO-OBJECT (срочность)",
    ("shift_transfer.py", "handle_transfer_confirmation"): "OWNER: create_transfer (not_your_shift)",
    ("shift_transfer.py", "handle_transfer_response"): "OWNER: accept/reject_transfer (not_your_transfer до статуса); test_shift_transfer_rebuild::test_foreign_executor_cannot_learn_transfer_status",
    ("shift_transfer.py", "handle_view_transfer"): "OWNER: менеджер — все, иначе участник; test_shift_transfer_rebuild::test_unit_view_transfer_idor_guard",
    ("shifts.py", "handle_shift_selection"): "OWNER: _load_shift_end_view; test_shifts_authz::test_shift_end_view_foreign_shift_is_invisible",
    ("shifts.py", "end_shift_yes_with_id"): "OWNER: _end_shift_by_id_unit (Shift.user_id)",
    ("shifts.py", "shifts_history_page"): "SELF",
    ("shifts.py", "shifts_filter_period"): "SELF",
    ("shifts.py", "shifts_filter_status"): "SELF",
    ("request_comments.py", "handle_add_comment_start"): "ACCESS: has_request_access_sync; test_comment_access_idor",
    ("request_comments.py", "handle_comment_type_selection"): "ACCESS: _apply_comment перепроверяет; test_comment_access_idor::test_apply_comment_rejects_foreign_request",
    ("request_comments.py", "handle_view_comments"): "ACCESS; test_comments_view",
    ("request_comments.py", "handle_view_comments_by_type"): "ACCESS (_load_comments_by_type_view)",
    ("request_comments.py", "handle_back_to_comments"): "ACCESS; test_comments_view",
    ("request_reports.py", "handle_view_report"): "ACCESS; test_report_view",
    ("request_reports.py", "handle_approve_request"): "OWNER + CANON (_load_applicant_action_context, not_owner)",
    ("request_reports.py", "handle_request_revision"): "OWNER + CANON (APPLICANT_RETURN)",
    ("user_apartment_selection.py", "process_yard_selection"): "BY-DESIGN: регистрация — выбор из справочника, привязка уходит на модерацию",
    ("user_apartment_selection.py", "process_building_selection"): "BY-DESIGN: то же",
    ("user_apartment_selection.py", "process_apartment_page"): "NO-OBJECT (страница)",
    ("user_apartment_selection.py", "process_apartment_selection"): "BY-DESIGN: заявка на привязку (pending → модерация)",
    ("user_apartments.py", "set_primary_apartment"): "OWNER: _set_primary_apartment (access_denied); test_bug_wave_p2_silent",
    ("user_apartments.py", "view_apartment_details"): "OWNER; test_user_apartments_admin_guard",
    ("feedback.py", "feedback_type"): "NO-OBJECT (тип отзыва)",
    ("access_control.py", "ac_vehicle_relation"): "NO-OBJECT (тип связи)",
    ("access_control.py", "ac_vehicle_apartment"): "OWNER: create_resident_request (ApartmentNotOwned); test_access_control_handler::test_vehicle_foreign_apartment_shows_error",
    ("access_control.py", "ac_pass_type"): "NO-OBJECT (тип пропуска)",
    ("access_control.py", "ac_pass_duration"): "NO-OBJECT (срок)",
    ("access_control.py", "ac_pass_apartment"): "OWNER: create_resident_pass (ApartmentNotOwned); access_control/tests/test_resident_api.py::test_create_pass_foreign_apartment_403",
    ("access_control.py", "ac_cancel_pass"): "OWNER: cancel_resident_pass (PassNotOwned); access_control/tests/test_resident_api.py::test_cancel_foreign_pass_403",
    ("access_control.py", "ac_dispute_response"): "OWNER: confirm_disputed_entry (EntryNotOwned); test_disputed_entry_callback",
    ("_role_gate.py", "deny_address_callback"): "NO-OBJECT (deny-роутер: только отказ)",
    ("base.py", "send_tutorial_video"): "NO-OBJECT (ключ ролика)",
    ("base.py", "switch_role"): "OWNER: целевая роль ∈ roles пользователя",
    ("group_intake.py", "group_intake_callback"): "OWNER: кандидат по (chat_id, message_id) из monitored-группы + _presser_allowed; test_group_intake_callbacks::test_foreign_presser_gets_alert_and_nothing_happens",
}

_STAFF_ROLES = frozenset({"admin", "manager", "engineer", "system_admin"})
_PARSES_ID = re.compile(
    r"(callback|call|cb|query|c)\.data[^\n]{0,80}(split|replace|removeprefix|\[len|int\(|rsplit|partition)"
    r"|int\((callback|call|cb|query)\.data|callback_data\.\w+|\.unpack\(|re\.match\(.{0,40}\.data"
    r"|parse_\w*\((callback|call|cb|query)\.data|_RE\.(?:match|fullmatch)\(|regexp\(")
_CHECK = r"(?:has_admin_access|has_manager_role|_guard|has_action_roles)"


def _action_roles(key: str) -> frozenset:
    from uk_management_bot.authz.catalog import get_action

    return frozenset(get_action(key).default_roles)


def _staff_gated(filters_chain, deco_src: str, body: str) -> bool:
    keys = re.findall(r"ActionGate\(([\w.]+)\)", " ".join(filters_chain))
    keys += re.findall(r'require_action\("([\w.]+)"\)', deco_src)
    if keys and all(_action_roles(k) <= _STAFF_ROLES for k in keys):
        return True
    deny = re.search(r"if not[^\n]*?(?:await )?" + _CHECK + r"\(|not in admin_ids", body)
    for var in re.findall(r"(\w+) = (?:await )?" + _CHECK + r"\(", body):
        deny = deny or re.search(r"if not " + var + r"\b", body)
    body_keys = re.findall(r'has_action_roles\([^,]+,\s*"([\w.]+)"', body)
    return bool(deny) and all(_action_roles(k) <= _STAFF_ROLES for k in body_keys)


def _live_object_callbacks() -> set[tuple[str, str]]:
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from uk_management_bot.group_intake_main import setup_group_intake_dispatcher
    from uk_management_bot.main import setup_routers

    handlers_dir = Path(ex.__file__).resolve().parents[1]
    out: set[tuple[str, str]] = set()

    def gates(router) -> list[str]:
        return [f"ActionGate({f.callback.action_key})"
                for f in router.callback_query._handler.filters or []
                if hasattr(f.callback, "action_key")]

    def walk(router, chain):
        chain = chain + gates(router)
        for h in router.callback_query.handlers:
            fn = inspect.unwrap(h.callback)
            lines, _ = inspect.getsourcelines(fn)
            src = "".join(lines)
            deco = "".join(line for line in lines if line.lstrip().startswith("@"))
            if _PARSES_ID.search(src) and not _staff_gated(chain, deco, src):
                rel = Path(inspect.getsourcefile(fn)).resolve().relative_to(handlers_dir)
                out.add((rel.as_posix(), fn.__name__))
        for sub in router.sub_routers:
            walk(sub, chain)

    for setup in (setup_routers, setup_group_intake_dispatcher):
        dp = Dispatcher(storage=MemoryStorage())
        setup(dp)
        try:
            for r in dp.sub_routers:
                walk(r, [])
        finally:
            # Роутеры — модульные синглтоны: отцепить, иначе следующий тест,
            # собирающий свой Dispatcher, упадёт «Router is already attached».
            for r in dp.sub_routers:
                r._parent_router = None
            dp.sub_routers.clear()
    return out


def test_every_object_callback_outside_staff_scope_is_registered():
    """Новый callback с id объекта, открытый не только персоналу, без записи —
    красный: сначала проверка принадлежности и пара тестов, потом запись."""
    live = _live_object_callbacks()
    assert live, "интроспекция роутеров ничего не нашла — сломан сам скан"
    assert sorted(live - set(BOT_IDOR_COVERAGE)) == []
    assert sorted(set(BOT_IDOR_COVERAGE) - live) == [], "запись без живого хендлера"


def test_registry_test_references_exist():
    """Ссылки реестра на тесты (`модуль::test_x`, модуль или тест этого файла) живые."""
    repo = Path(__file__).resolve().parents[3]
    here = Path(__file__).read_text(encoding="utf-8")

    def modules(stem: str) -> list[Path]:
        return [p for p in repo.glob(f"**/{stem}.py")
                if not {".claude", "node_modules", ".venv"} & set(p.relative_to(repo).parts)]

    missing = []
    for ref in BOT_IDOR_COVERAGE.values():
        pairs = re.findall(r"([\w/.]+?)(?:\.py)?::(test_\w+)", ref)
        for module, name in pairs:
            if not any(f"def {name}(" in m.read_text(encoding="utf-8") for m in modules(Path(module).name)):
                missing.append(f"{module}::{name}")
        bare = re.sub(r"[\w/.]+::test_\w+", "", ref)
        for name in re.findall(r"(?<![\w/])(test_\w+)", bare):
            if f"def {name}(" not in here and not modules(name):
                missing.append(name)
    assert missing == [], missing
