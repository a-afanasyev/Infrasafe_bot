"""Гейт против возврата класса «незащищённый хендлер» (аудит 2026-08-18).

Дискриминатор — ПРОИСХОЖДЕНИЕ идентификатора, не «свои/чужие»: хендлер берёт
id из callback.data И идёт в БД И не имеет признака авторизации → обязан иметь
запись в BASELINE с обоснованием. Автоматически различить «свои данные» нельзя
(admin_approve_apartment использовал from_user.id и выглядел «своим»).

Признаки авторизации (см. план аудита):
  * @require_role на хендлере;
  * вызов has_admin_access / has_executor_access / check_user_role[_sync] /
    has_request_access_sync / request_access_reason_sync — С ИСПОЛЬЗОВАНИЕМ
    результата в условии (голый вызов не считается);
  * канон run_command_sync/async (авторизует внутри по PrincipalRef);
  * роутер модуля несёт RoleGate (module-level идиома волны A/D).

НЕ признаки: StateFilter (даёт ложную гарантию); ownership-сравнение — оно
живёт только КАТЕГОРИЕЙ в BASELINE (OWNER-CHECK@...), иначе фильтр запроса
`User.telegram_id == tid` сходил бы за guard и прятал реальную дыру.

Категории BASELINE: OWNER-CHECK@юнит (владение фильтруется в SQL/юните),
SERVICE-CHECK@сервис (роль проверяет сервис), SELF (выборка от from_user.id),
REVIEW→BUG-176 (кандидат не разобран — рабочий список, НЕ оправдание).
Записи REVIEW разбираются отдельной волной; их исчезновение из кандидатов
(например, после гейта их модуля) тоже красное — двунаправленность.
"""
from __future__ import annotations

import ast
from pathlib import Path

HANDLERS_DIR = Path(__file__).resolve().parents[2] / "uk_management_bot" / "handlers"

AUTH_CALLS = {
    "has_admin_access", "has_executor_access", "check_user_role",
    "check_user_role_sync", "has_request_access_sync", "request_access_reason_sync",
}
CANON_CALLS = {"run_command_sync", "run_command_async"}
DATA_CALLS = {"query", "run_db", "session_scope", "execute", "add", "commit", "delete"}

# ══════════════════════════════════════════════════════════════════════════════
# BASELINE — каждый кандидат обязан быть здесь; новый кандидат = красный тест.
# ══════════════════════════════════════════════════════════════════════════════
BASELINE = {
    # Проверено чтением в волнах B/D (PR I/II):
    ("user_apartments.py", "set_primary_apartment"): "OWNER-CHECK@_set_primary_apartment (access_denied при чужом from_user)",
    ("user_apartments.py", "view_apartment_details"): "OWNER-CHECK@handler (user_telegram_id != from_user.id → отказ)",
    ("shifts.py", "handle_shift_selection"): "OWNER-CHECK@_load_shift_end_view (D3: Shift.user_id == owner.id)",
    ("shifts.py", "end_shift_yes_with_id"): "OWNER-CHECK@_end_shift_by_id_unit (Shift.user_id == user.id)",
    ("shifts.py", "force_end_shift"): "SERVICE-CHECK@ShiftService.force_end_shift (роль менеджера в сервисе, результат используется)",
    ("shifts.py", "shifts_history_page"): "SELF (история своих смен от from_user.id; id страницы из callback — не объект)",
    ("shifts.py", "shifts_filter_period"): "SELF (фильтр собственной истории)",
    ("shifts.py", "shifts_filter_status"): "SELF (фильтр собственной истории)",
    ("request_acceptance.py", "view_completion_media"): "OWNER-CHECK@_load_completion_media (from_user.id, вердикт forbidden)",
    # user_management/user_verification выпали из кандидатов: у них рукописный
    # ролевой guard в условии (any(role in ['admin','manager'])), секревью
    # подтвердило пять самых опасных построчно — VERIFIED-SAFE.
    # Кандидаты волны-2 (BUG-176): происхождение id из callback подтверждено,
    # авторизация НЕ подтверждена чтением — рабочий список, не оправдание.
    ("access_control.py", "ac_vehicle_relation"): "REVIEW→BUG-176",
    ("access_control.py", "ac_vehicle_apartment"): "REVIEW→BUG-176",
    ("access_control.py", "ac_pass_duration"): "REVIEW→BUG-176",
    ("access_control.py", "ac_pass_apartment"): "REVIEW→BUG-176",
    ("access_control.py", "ac_cancel_pass"): "REVIEW→BUG-176",
    ("access_control.py", "ac_dispute_response"): "REVIEW→BUG-176",
    ("inspector_requests.py", "inspector_yard_page"): "REVIEW→BUG-176",
    ("inspector_requests.py", "inspector_yard_selected"): "REVIEW→BUG-176",
    ("inspector_requests.py", "inspector_building_page"): "REVIEW→BUG-176",
    ("inspector_requests.py", "inspector_building_selected"): "REVIEW→BUG-176",
    ("profile_editing.py", "handle_language_choice"): "SELF (смена СВОЕГО языка; значение из callback — не id объекта)",
    ("request_acceptance.py", "view_completed_request"): "REVIEW→BUG-176",
    ("request_acceptance.py", "save_rating"): "REVIEW→BUG-176",
    ("request_reports.py", "handle_back_to_report"): "REVIEW→BUG-176",
    ("requests/create.py", "handle_address_selection"): "SELF (выбор адреса в СВОЁМ черновике заявки)",
    ("user_apartment_selection.py", "process_yard_selection"): "SELF (шаг выбора из справочника для СВОЕЙ заявки на привязку; итог — pending, одобряет менеджер)",
    ("user_apartment_selection.py", "process_building_selection"): "SELF (шаг выбора из справочника для СВОЕЙ заявки на привязку)",
    ("user_apartment_selection.py", "process_apartment_selection"): "SELF (шаг выбора из справочника для СВОЕЙ заявки на привязку)",
    ("requests/listing.py", "handle_back_to_list"): "REVIEW→BUG-176",
    ("shift_transfer.py", "handle_shift_selection"): "REVIEW→BUG-176",
    ("shift_transfer.py", "handle_reason_selection"): "REVIEW→BUG-176",
    ("shift_transfer.py", "handle_urgency_selection"): "REVIEW→BUG-176",
    ("shift_transfer.py", "handle_transfer_confirmation"): "REVIEW→BUG-176",
}


def _calls_in(node) -> set:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name:
                out.add(name)
    return out


def _auth_call_used_in_condition(fns) -> bool:
    """Auth-вызов считается только при использовании результата: имя вызова
    встречается в тексте условия if/while/assert либо в return-выражении."""
    for fn in fns:
        for node in ast.walk(fn):
            tests = []
            if isinstance(node, (ast.If, ast.While)):
                tests.append(node.test)
            elif isinstance(node, ast.Assert):
                tests.append(node.test)
            elif isinstance(node, ast.Return) and node.value is not None:
                tests.append(node.value)
            for t in tests:
                src = ast.unparse(t)
                if any(a in src for a in AUTH_CALLS):
                    return True
    # присваивание результата с последующим условием по имени переменной
    for fn in fns:
        assigned = set()
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
                name = getattr(node.value.func, "id", None) or getattr(node.value.func, "attr", None)
                if name in AUTH_CALLS:
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            assigned.add(tgt.id)
        if assigned:
            for node in ast.walk(fn):
                if isinstance(node, (ast.If, ast.While)) and any(
                    v in ast.unparse(node.test) for v in assigned
                ):
                    return True
    return False


def _inline_role_guard(fns) -> bool:
    """Рукописный ролевой guard: условие if/while со сравнением по СПИСКУ РОЛЕЙ
    (`any(role in ['admin','manager'] ...)`). Признак — только в условии;
    упоминание роли вне условия guard'ом не считается."""
    for fn in fns:
        for node in ast.walk(fn):
            if not isinstance(node, (ast.If, ast.While)):
                continue
            src = ast.unparse(node.test)
            if ("role" in src) and ("'manager'" in src or '"manager"' in src
                                    or "'admin'" in src or '"admin"' in src):
                return True
    return False


def _module_gated(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if "RoleGate" in src and ".filter(RoleGate(" in src:
        return True
    pkg_router = path.parent / "_router.py"
    return pkg_router.exists() and ".filter(RoleGate(" in pkg_router.read_text(encoding="utf-8")


def _candidates():
    """(rel_path, fn_name) хендлеров: id из callback.data + БД + нет признака."""
    out = []
    for path in sorted(HANDLERS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        gated = _module_gated(path)
        local = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in local.values():
            decos = [ast.unparse(d) for d in fn.decorator_list]
            if not any(".callback_query" in d for d in decos):
                continue
            if any("require_role" in d for d in decos) or gated:
                continue
            body_src = ast.unparse(fn)
            takes_id = "callback.data" in body_src and any(
                x in body_src for x in ("split", "replace", "int(")
            )
            if not takes_id:
                continue
            # транзитивное раскрытие вызовов того же модуля (2 уровня)
            seen, frontier = set(), {fn.name}
            for _ in range(3):
                nxt = set()
                for name in frontier:
                    if name in seen or name not in local:
                        continue
                    seen.add(name)
                    nxt |= _calls_in(local[name])
                frontier = nxt
            closure = [local[n] for n in seen if n in local]
            all_calls = set()
            for f in closure:
                all_calls |= _calls_in(f)
            if not (all_calls & DATA_CALLS):
                continue
            if all_calls & CANON_CALLS:
                continue
            if (all_calls & AUTH_CALLS) and _auth_call_used_in_condition(closure):
                continue
            if _inline_role_guard(closure):
                continue
            out.append((str(path.relative_to(HANDLERS_DIR)), fn.name))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Ратчет
# ══════════════════════════════════════════════════════════════════════════════

def test_every_candidate_is_in_baseline():
    candidates = set(_candidates())
    assert candidates, "скан не нашёл ни одного кандидата — сломан сам скан"

    new = candidates - set(BASELINE)
    assert not new, (
        f"Новые хендлеры с id из callback.data + БД без признака авторизации: "
        f"{sorted(new)}. Добавьте авторизацию (канон: @require_role / RoleGate / "
        f"has_request_access_sync) либо запись в BASELINE с обоснованием."
    )

    gone = set(BASELINE) - candidates
    assert not gone, (
        f"Записи BASELINE больше не являются кандидатами: {sorted(gone)}. "
        f"Если хендлер защищён/удалён — уберите запись (двунаправленность)."
    )


def test_baseline_not_empty_and_categorized():
    assert len(BASELINE) >= 25
    assert all(v for v in BASELINE.values())


# ══════════════════════════════════════════════════════════════════════════════
# Самозащита скана
# ══════════════════════════════════════════════════════════════════════════════

_OFFENDER = '''
@router.callback_query(F.data.startswith("thing_"))
async def synthetic_offender(callback, state):
    thing_id = int(callback.data.split("_")[-1])
    with session_scope() as db:
        db.query(Thing).filter(Thing.id == thing_id).first()
'''

_BARE_CALL = '''
@router.callback_query(F.data.startswith("thing_"))
async def bare_call(callback, state):
    thing_id = int(callback.data.split("_")[-1])
    has_admin_access(roles=None)  # результат НЕ используется
    with session_scope() as db:
        db.query(Thing).filter(Thing.id == thing_id).first()
'''

_WHERE_ONLY = '''
@router.callback_query(F.data.startswith("thing_"))
async def where_only(callback, state):
    thing_id = int(callback.data.split("_")[-1])
    with session_scope() as db:
        db.query(Thing).filter(User.telegram_id == callback.from_user.id).first()
'''

_GUARDED = '''
@router.callback_query(F.data.startswith("thing_"))
async def guarded(callback, state, roles=None, user=None):
    thing_id = int(callback.data.split("_")[-1])
    if not has_admin_access(roles=roles, user=user):
        return
    with session_scope() as db:
        db.query(Thing).filter(Thing.id == thing_id).first()
'''


def _scan_snippet(code: str):
    tree = ast.parse(code)
    local = {n.name: n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    fn = next(iter(local.values()))
    body_src = ast.unparse(fn)
    takes_id = "callback.data" in body_src and any(
        x in body_src for x in ("split", "replace", "int("))
    all_calls = _calls_in(fn)
    touches_db = bool(all_calls & DATA_CALLS)
    auth = bool(all_calls & AUTH_CALLS) and _auth_call_used_in_condition([fn])
    return takes_id and touches_db and not auth


def test_scanner_detects_synthetic_offender():
    assert _scan_snippet(_OFFENDER)


def test_scanner_ignores_bare_auth_call_without_usage():
    """Голый вызов has_admin_access без использования результата — НЕ guard."""
    assert _scan_snippet(_BARE_CALL)


def test_scanner_does_not_count_where_clause_as_guard():
    """Фильтр запроса `User.telegram_id == ...` — не признак авторизации."""
    assert _scan_snippet(_WHERE_ONLY)


def test_scanner_accepts_condition_guarded_handler():
    assert not _scan_snippet(_GUARDED)
