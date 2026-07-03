"""PR2-pre (SSOT-кластер #1): read-инвентаризация workflow-полей — гейт.

Зеркало write-гейта (test_workflow_inventory.py) для ЧТЕНИЙ: фиксирует
текущий набор сырых сравнений/фильтров по workflow-полям заявки как baseline.
До первого canonical-writer (PR2a) каждое сырое чтение должно быть либо
переведено на парный предикат (utils/workflow_predicates.py), либо остаться
здесь осознанно. Пропущенный legacy-guard сломается сразу после PR2a —
этот гейт делает пропуск невозможным.

Ловит:
  - сравнения `<recv>.<field> == / != / in / not in ...` (Python и SQL-колонки
    Request.<field> == ... выглядят в AST одинаково — Compare);
  - `.in_([...])` / `.is_(...)` / `.isnot(...)` вызовы на workflow-атрибутах;
  - truthiness-guard'ы `if <recv>.manager_confirmed:` / `not <recv>.is_returned`
    для булевых флагов.

Для поля `status` учитываются только request-подобные receivers (User/Shift/
Assignment имеют своё поле status); флаги/timestamps — любые receivers.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"

READ_FIELDS = frozenset({"manager_confirmed", "is_returned"})
STATUS_FIELD = "status"
REQUEST_RECEIVERS = frozenset({
    "request", "req", "r", "db_request", "existing", "target_request",
    "new_request", "Request", "RequestModel",
})
EXCLUDED_PARTS = {"tests", "__pycache__"}
# Сам модуль предикатов и SSOT-ядро — единственные легальные места сырых чтений
ALLOWLIST_FILES = {
    "uk_management_bot/utils/workflow_predicates.py",
    "uk_management_bot/utils/request_workflow.py",
}


def _recv(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def _interesting(field: str, receiver: str) -> bool:
    if field in READ_FIELDS:
        return True
    return field == STATUS_FIELD and receiver in REQUEST_RECEIVERS


def _attr_sites(node: ast.expr) -> set[tuple[str, str]]:
    """(receiver, field) для интересных Attribute-узлов внутри выражения."""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and _interesting(sub.attr, _recv(sub.value)):
            out.add((_recv(sub.value), sub.attr))
    return out


def collect_read_sites(root: Path = PACKAGE_ROOT) -> set[tuple[str, str, str]]:
    sites: set[tuple[str, str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        if EXCLUDED_PARTS & set(path.parts) or path.name.startswith("test_"):
            continue
        rel = str(path.relative_to(root.parent))
        if rel in ALLOWLIST_FILES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # сравнения: x.status == "...", Request.status == ..., in [...]
            if isinstance(node, ast.Compare):
                for recv, fieldname in _attr_sites(node.left):
                    sites.add((rel, f"cmp:{recv}", fieldname))
            # .in_(...)/.is_(...)/.isnot(...) на атрибуте
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("in_", "is_", "isnot", "notin_"):
                    inner = node.func.value
                    if isinstance(inner, ast.Attribute) and \
                            _interesting(inner.attr, _recv(inner.value)):
                        sites.add((rel, f"{node.func.attr}:{_recv(inner.value)}",
                                   inner.attr))
            # truthiness булевых флагов: if x.manager_confirmed / not x.is_returned
            elif isinstance(node, (ast.If, ast.IfExp)):
                test = node.test
                checks = [test]
                if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
                    checks.append(test.operand)
                if isinstance(test, ast.BoolOp):
                    checks.extend(test.values)
                for ch in checks:
                    if isinstance(ch, ast.Attribute) and ch.attr in READ_FIELDS:
                        sites.add((rel, f"if:{_recv(ch.value)}", ch.attr))
    return sites


# ---------------------------------------------------------------------------
# BASELINE — PR2-pre/1 (2026-06-10), сжат в PR2-pre/2 (2026-06-10).
#
# PR2-pre/2 мигрировал на парные предикаты ВСЮ composite-flag поверхность
# (manager_confirmed/is_returned) — единственное, что ломается при canonical-
# write модели A (Выполнена+confirmed → Исполнено). Это admin.py (dashboard-
# счётчики/списки + keyboard-блок) и unaccepted_requests.py (полностью).
#
# Оставшиеся записи — ОСОЗНАННО сырые, по категориям:
#   • FALSE-POSITIVE — receiver не заявка (User/resident/membership/shift),
#     помечены инлайн;
#   • status-фильтры, НЕ затрагиваемые нормализацией A (NEW/active/Уточнение/
#     Отменена/closed-наборы, навигация, дисптч/оптимизаторы/метрики) —
#     значения статусов сохраняются по обе стороны cutover;
#   • DEFER→PR2a — request_reports.py (status==Исполнено): под каноном смысл
#     «Исполнено» раздваивается, решение принимается с writer'ом;
#   • API-ответы/reconciliation — проекция project_*_status ОТЛОЖЕНА до
#     cutover (PR3/PR4): отличается от identity только для статуса «Возвращена»,
#     а он не пишется в БД до backfill → сейчас инертна (решение 2026-06-10).
# ---------------------------------------------------------------------------

BASELINE: set[tuple[str, str, str]] = {
    ('uk_management_bot/api/dependencies_access.py', 'cmp:request', 'status'),
    ('uk_management_bot/api/public/router.py', 'cmp:RequestModel', 'status'),
    ('uk_management_bot/api/public/router.py', 'in_:RequestModel', 'status'),
    # FALSE-POSITIVE (подтверждено PR2-pre/2): existing = User, status "blocked"/
    # "approved" (router.py:50,52) — не workflow заявки.
    ('uk_management_bot/api/registration/router.py', 'cmp:existing', 'status'),
    ('uk_management_bot/api/requests/router.py', 'cmp:RequestModel', 'status'),
    # PR4 cutover: kanban-группировка переведена с сырого `r.status == st` на
    # проецированный `card.status == st` (project_public_status в
    # _make_request_card) → 'cmp:r' status в этом файле исчез.
    ('uk_management_bot/api/requests/router.py', 'cmp:req', 'status'),
    ('uk_management_bot/api/requests/stats_router.py', 'in_:Request', 'status'),
    ('uk_management_bot/api/shifts/service.py', 'in_:Request', 'status'),
    # REG-02: _move_active_requests_web фильтрует заявки активных статусов перед
    # status-preserving переносом при reassign смены (набор-фильтр, не переход).
    ('uk_management_bot/api/shifts/service.py', 'cmp:req', 'status'),
    # одноразовый migration-скрипт (write-гейт уже фиксирует его update())
    # FALSE-POSITIVE/вне scope (подтверждено PR2-pre/2): self.request.status in
    # ["completed","cancelled"] (shift_assignment.py:212) — non-canon значения,
    # подсистема смен (вне scope), фактически всегда False.
    ('uk_management_bot/database/models/shift_assignment.py', 'cmp:request', 'status'),
    # FALSE-POSITIVE (подтверждено PR2-pre/2): r = resident (UserApartment),
    # status 'approved'/'pending'/'rejected' (address_apartments.py:377-379).
    ('uk_management_bot/handlers/address_apartments.py', 'cmp:r', 'status'),
    # PR2-pre/2: composite-флаги (manager_confirmed/is_returned) admin.py
    # мигрированы на предикаты awaiting_manager/awaiting_applicant/returned_for_review.
    # PR-29.3 (ARCH-01): class-level query-выражения `Request.status == ...` /
    # `Request.status.in_([...])` (cmp:Request / in_:Request) переехали вместе с
    # ORM-слоем в services/admin_handler_service.py (см. ниже). В хендлере
    # остаются ТОЛЬКО сравнения статуса/флага на УЖЕ ЗАГРУЖЕННОМ объекте
    # (выбор клавиатуры/текста UI): cmp:r/cmp:request status + if:r is_returned.
    # AUD3-06: admin.py разбит на пакет handlers/admin/ — те же UI-сравнения,
    # разнесены по под-модулям views/lists/actions/materials.
    ('uk_management_bot/handlers/admin/actions.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/admin/lists.py', 'cmp:r', 'status'),
    ('uk_management_bot/handlers/admin/lists.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/admin/lists.py', 'if:r', 'is_returned'),
    ('uk_management_bot/handlers/admin/materials.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/clarification_replies.py', 'cmp:request', 'status'),
    # PR2a-6: request_reports.py:118,239 переведены на is_awaiting_applicant
    # (возвращённые исключены) — сняты из read-baseline.
    ('uk_management_bot/handlers/request_status_management.py', 'in_:Request', 'status'),
    # PR-29.2 (ARCH-01): cmp:r/req/request — сравнения статуса на УЖЕ
    # ЗАГРУЖЕННОМ объекте (выбор клавиатуры/ветки UI) — ОСТАЮТСЯ в хендлере.
    # AUD3-06: requests.py разбит на пакет handlers/requests/ — те же UI-сравнения
    # разнесены по под-модулям listing/myrequests.
    ('uk_management_bot/handlers/requests/listing.py', 'cmp:r', 'status'),
    ('uk_management_bot/handlers/requests/listing.py', 'cmp:req', 'status'),
    ('uk_management_bot/handlers/requests/listing.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/requests/myrequests.py', 'cmp:r', 'status'),
    ('uk_management_bot/handlers/requests/myrequests.py', 'cmp:request', 'status'),
    # PR-29.2: `Request.status.in_([...])` в запросах переехал из хендлера в
    # services/request_handler_service.py (см. ниже) вместе с ORM-слоем.
    ('uk_management_bot/handlers/shifts.py', 'in_:Request', 'status'),
    # PR2-pre/2: unaccepted_requests.py ПОЛНОСТЬЮ мигрирован на
    # is_awaiting_applicant / awaiting_applicant_clause — сырых чтений не осталось.
    # FALSE-POSITIVE (подтверждено PR2-pre/2): existing = членство в адресе,
    # status "pending"/"approved"/"rejected" (addresses/core.py:483-487).
    ('uk_management_bot/services/addresses/core.py', 'cmp:existing', 'status'),
    # PR-29.3 (ARCH-01): ORM manager/admin-хендлера заявок вынесен сюда из
    # handlers/admin.py — `Request.status == ...` (NEW/EXECUTED/Закуп точечные
    # фильтры списков) и `Request.status.in_([...])` (active/archive-наборы).
    # Это status-фильтры, НЕ затрагиваемые канон-нормализацией A: значения
    # статусов сохраняются по обе стороны cutover.
    ('uk_management_bot/services/admin_handler_service.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/admin_handler_service.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/metrics_manager.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/recommendation_engine.py', 'cmp:Request', 'status'),
    # PR-29.2 (ARCH-01): ORM resident/executor-хендлера заявок вынесен сюда из
    # handlers/requests.py — `Request.status.in_([...])` в list/pagination/pool
    # запросах. Это status-фильтры (NEW/active/archive-наборы), НЕ затрагиваемые
    # канон-нормализацией A: значения статусов сохраняются по обе стороны cutover.
    ('uk_management_bot/services/request_handler_service.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/request_service.py', 'cmp:Request', 'status'),
    # DED-01: `cmp:request`-чтение удалено вместе с мёртвым
    # is_role_allowed_for_transition (авторизацию решает канон workflow).
    ('uk_management_bot/services/shift_analytics.py', 'cmp:r', 'status'),
    ('uk_management_bot/services/shift_analytics.py', 'cmp:request', 'status'),
    ('uk_management_bot/services/shift_assignment_service.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/shift_assignment_service.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/shift_transfer_service.py', 'in_:Request', 'status'),
    # REG-02: _move_active_requests фильтрует заявки активных статусов перед
    # status-preserving переносом (В работе/Закуп/Уточнение) — это набор-фильтр
    # переноса, НЕ workflow-переход (канон-нормализация A не затрагивается).
    ('uk_management_bot/services/shift_transfer_service.py', 'cmp:req', 'status'),
    ('uk_management_bot/services/smart_dispatcher.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/webhook_sender.py', 'cmp:r', 'status'),
    ('uk_management_bot/utils/request_helpers.py', 'cmp:request', 'status'),
}


def test_workflow_read_sites_match_baseline():
    actual = collect_read_sites()
    new_sites = actual - BASELINE
    gone = BASELINE - actual
    msg = []
    if new_sites:
        msg.append("НОВЫЕ сырые чтения workflow-полей (используйте парные "
                   "предикаты utils/workflow_predicates.py):\n" +
                   "\n".join(f"  {s!r}," for s in sorted(new_sites)))
    if gone:
        msg.append("Исчезнувшие чтения (переведены на предикаты? обновите baseline):\n"
                   + "\n".join(f"  {s!r}," for s in sorted(gone)))
    assert not msg, "\n\n".join(msg)
