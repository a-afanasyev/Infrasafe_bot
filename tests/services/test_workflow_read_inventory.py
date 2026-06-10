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
    ('uk_management_bot/api/requests/router.py', 'cmp:r', 'status'),
    ('uk_management_bot/api/requests/router.py', 'cmp:req', 'status'),
    ('uk_management_bot/api/requests/stats_router.py', 'in_:Request', 'status'),
    ('uk_management_bot/api/shifts/router.py', 'in_:Request', 'status'),
    # одноразовый migration-скрипт (write-гейт уже фиксирует его update())
    ('uk_management_bot/database/migrations/fix_manager_confirmed_legacy.py', 'cmp:Request', 'manager_confirmed'),
    ('uk_management_bot/database/migrations/fix_manager_confirmed_legacy.py', 'cmp:Request', 'status'),
    # FALSE-POSITIVE/вне scope (подтверждено PR2-pre/2): self.request.status in
    # ["completed","cancelled"] (shift_assignment.py:212) — non-canon значения,
    # подсистема смен (вне scope), фактически всегда False.
    ('uk_management_bot/database/models/shift_assignment.py', 'cmp:request', 'status'),
    # FALSE-POSITIVE (подтверждено PR2-pre/2): r = resident (UserApartment),
    # status 'approved'/'pending'/'rejected' (address_apartments.py:377-379).
    ('uk_management_bot/handlers/address_apartments.py', 'cmp:r', 'status'),
    # PR2-pre/2: composite-флаги (manager_confirmed/is_returned) admin.py
    # мигрированы на предикаты awaiting_manager/awaiting_applicant/returned_for_review.
    # Остаются простые status-фильтры, НЕ затрагиваемые канон-нормализацией A
    # (NEW/active-навигация :853-884) + display-маркер возврата (:882/:1167).
    ('uk_management_bot/handlers/admin.py', 'cmp:Request', 'status'),
    ('uk_management_bot/handlers/admin.py', 'cmp:r', 'status'),
    ('uk_management_bot/handlers/admin.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/admin.py', 'if:r', 'is_returned'),
    ('uk_management_bot/handlers/admin.py', 'in_:Request', 'status'),
    ('uk_management_bot/handlers/clarification_replies.py', 'cmp:request', 'status'),
    # DEFER→PR2a: status==Исполнено (request_reports.py:118,239) — под каноном
    # «Исполнено» раздваивается (confirmed-awaiting vs returned); продуктовое
    # решение принимается вместе с canonical-writer.
    ('uk_management_bot/handlers/request_reports.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/request_status_management.py', 'in_:Request', 'status'),
    ('uk_management_bot/handlers/requests.py', 'cmp:r', 'status'),
    ('uk_management_bot/handlers/requests.py', 'cmp:req', 'status'),
    ('uk_management_bot/handlers/requests.py', 'cmp:request', 'status'),
    ('uk_management_bot/handlers/requests.py', 'in_:Request', 'status'),
    ('uk_management_bot/handlers/shifts.py', 'in_:Request', 'status'),
    # PR2-pre/2: unaccepted_requests.py ПОЛНОСТЬЮ мигрирован на
    # is_awaiting_applicant / awaiting_applicant_clause — сырых чтений не осталось.
    # FALSE-POSITIVE (подтверждено PR2-pre/2): existing = членство в адресе,
    # status "pending"/"approved"/"rejected" (addresses/core.py:483-487).
    ('uk_management_bot/services/addresses/core.py', 'cmp:existing', 'status'),
    ('uk_management_bot/services/assignment_optimizer.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/async_request_service.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/async_request_service.py', 'cmp:request', 'status'),
    ('uk_management_bot/services/async_shift_assignment_service.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/async_smart_dispatcher.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/geo_optimizer.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/metrics_manager.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/recommendation_engine.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/request_service.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/request_service.py', 'cmp:request', 'status'),
    ('uk_management_bot/services/shift_analytics.py', 'cmp:r', 'status'),
    ('uk_management_bot/services/shift_analytics.py', 'cmp:request', 'status'),
    ('uk_management_bot/services/shift_assignment_service.py', 'cmp:Request', 'status'),
    ('uk_management_bot/services/shift_assignment_service.py', 'in_:Request', 'status'),
    ('uk_management_bot/services/shift_transfer_service.py', 'in_:Request', 'status'),
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
