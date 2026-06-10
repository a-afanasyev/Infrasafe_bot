"""PR1 (SSOT-кластер #1): AST-инвентаризация write-сайтов workflow-полей.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует ТЕКУЩИЙ набор мест, мутирующих workflow-поля
заявки, как ожидаемый. Появление нового сайта (или исчезновение старого)
ломает тест ОСОЗНАННО:
  - новый сайт мутации → должен идти через mutation-layer (PR2) либо быть
    явно добавлен сюда с обоснованием;
  - исчезнувший сайт → переведён на layer, удалить из baseline (PR2a-c
    инкрементально сжимают этот список до allowlist-ядра).

Ловит (по всему production-пакету, вкл. database/migrations):
  - attribute-присваивания `<recv>.<field> = ...` (Assign/AugAssign/AnnAssign);
  - `setattr(obj, "<field>", ...)`;
  - `update(...).values(<field>=...)` / `query.update({...})`;
  - конструкторы `Request(...)`/`RequestModel(...)` с workflow-полями.

Для поля `status` (имя слишком общее: User/Shift/Assignment) учитываются
только request-подобные receivers; остальные поля — любые receivers.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"

# Workflow/assignment-поля заявки (ownership-список плана, PR2)
WORKFLOW_FIELDS = frozenset({
    "manager_confirmed", "manager_confirmed_by", "manager_confirmed_at",
    "manager_confirmation_notes",
    "is_returned", "returned_at", "returned_by", "return_reason", "return_media",
    "completed_at", "requested_materials", "completion_report", "completion_media",
    "executor_id", "assigned_at", "assigned_by", "assignment_type", "assigned_group",
})
STATUS_FIELD = "status"
# receivers, трактуемые как заявка (для поля status)
REQUEST_RECEIVERS = frozenset({
    "request", "req", "db_request", "existing", "target_request", "new_request",
})
REQUEST_CTORS = frozenset({"Request", "RequestModel"})

EXCLUDED_PARTS = {"tests", "__pycache__"}


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def _interesting_field(field: str, receiver: str) -> bool:
    if field in WORKFLOW_FIELDS:
        return True
    return field == STATUS_FIELD and receiver in REQUEST_RECEIVERS


def collect_write_sites(root: Path = PACKAGE_ROOT) -> set[tuple[str, str, str]]:
    """→ {(relpath, kind:receiver, field)} по всем .py production-пакета."""
    sites: set[tuple[str, str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        if EXCLUDED_PARTS & set(path.parts):
            continue
        if path.name.startswith("test_"):
            continue
        rel = str(path.relative_to(root.parent))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # <recv>.<field> = ...
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for tgt in targets:
                if isinstance(tgt, ast.Attribute):
                    recv = _receiver_name(tgt.value)
                    if _interesting_field(tgt.attr, recv):
                        sites.add((rel, f"attr:{recv}", tgt.attr))
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            # setattr(obj, "field", ...)
            if isinstance(fn, ast.Name) and fn.id == "setattr" and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    recv = _receiver_name(node.args[0])
                    if _interesting_field(arg.value, recv):
                        sites.add((rel, f"setattr:{recv}", arg.value))
            # update(...).values(field=...) / .values({...})
            if isinstance(fn, ast.Attribute) and fn.attr in ("values", "update"):
                for kw in node.keywords or []:
                    if kw.arg and _interesting_field(kw.arg, "values"):
                        sites.add((rel, f"{fn.attr}()", kw.arg))
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        for k in arg.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                                    and _interesting_field(k.value, "values"):
                                sites.add((rel, f"{fn.attr}()", k.value))
            # Request(field=...) конструкторы
            ctor = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if ctor in REQUEST_CTORS:
                for kw in node.keywords or []:
                    if kw.arg and (kw.arg in WORKFLOW_FIELDS or kw.arg == STATUS_FIELD):
                        sites.add((rel, f"ctor:{ctor}", kw.arg))
    return sites


# ---------------------------------------------------------------------------
# BASELINE — текущее фактическое состояние (зафиксировано PR1, 2026-06-10).
# PR2a-c переводят сайты на mutation-layer и СЖИМАЮТ этот список; целевое
# ядро-allowlist = mutation-layer + assignment-сервис + create-фабрика.
#
# Группы:
#   - shift_*-файлы и database/models/shift_*: поля СМЕН (completed_at/
#     assigned_at на Shift/ShiftTransfer) — машина статусов смен вне scope
#     кластера #1, останутся вне layer заявок (одноимённые поля, фиксируем
#     как шум-инвариант);
#   - database/migrations/fix_manager_confirmed_legacy.py: одноразовый
#     migration-скрипт (план, риск №30) — allowlist с обоснованием;
#   - остальное — write-сайты заявки, мигрируют в PR2a (handlers), PR2b
#     (api), PR2c (services/dispatcher).
# ---------------------------------------------------------------------------

BASELINE: set[tuple[str, str, str]] = {
    ('uk_management_bot/api/callcenter/router.py', 'ctor:Request', 'status'),
    ('uk_management_bot/api/requests/router.py', 'ctor:RequestModel', 'status'),
    ('uk_management_bot/api/shifts/router.py', 'attr:req', 'executor_id'),
    ('uk_management_bot/api/shifts/router.py', 'attr:transfer', 'assigned_at'),
    ('uk_management_bot/database/migrations/fix_manager_confirmed_legacy.py', 'update()', 'manager_confirmed'),
    ('uk_management_bot/database/models/shift_assignment.py', 'attr:self', 'completed_at'),
    ('uk_management_bot/database/models/shift_transfer.py', 'attr:self', 'assigned_at'),
    ('uk_management_bot/database/models/shift_transfer.py', 'attr:self', 'completed_at'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'assigned_group'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'completed_at'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'is_returned'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'manager_confirmed'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'manager_confirmed_at'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'manager_confirmed_by'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'requested_materials'),
    ('uk_management_bot/handlers/admin.py', 'attr:request', 'status'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'completed_at'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'is_returned'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'manager_confirmed'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'return_media'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'return_reason'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'returned_at'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'returned_by'),
    ('uk_management_bot/handlers/request_acceptance.py', 'attr:request', 'status'),
    ('uk_management_bot/handlers/request_status_management.py', 'attr:request', 'completion_report'),
    ('uk_management_bot/handlers/request_status_management.py', 'attr:request', 'requested_materials'),
    ('uk_management_bot/handlers/requests.py', 'attr:request', 'completion_media'),
    ('uk_management_bot/handlers/requests.py', 'attr:request', 'status'),
    ('uk_management_bot/handlers/requests.py', 'ctor:Request', 'status'),
    ('uk_management_bot/handlers/unaccepted_requests.py', 'attr:request', 'manager_confirmation_notes'),
    ('uk_management_bot/handlers/unaccepted_requests.py', 'attr:request', 'manager_confirmed'),
    ('uk_management_bot/handlers/unaccepted_requests.py', 'attr:request', 'manager_confirmed_at'),
    ('uk_management_bot/handlers/unaccepted_requests.py', 'attr:request', 'manager_confirmed_by'),
    ('uk_management_bot/handlers/unaccepted_requests.py', 'attr:request', 'status'),
    ('uk_management_bot/services/assignment_optimizer.py', 'attr:req_assignment', 'executor_id'),
    ('uk_management_bot/services/assignment_optimizer.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_group'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_group'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/async_request_service.py', 'attr:request', 'completed_at'),
    ('uk_management_bot/services/async_request_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/async_request_service.py', 'attr:request', 'status'),
    ('uk_management_bot/services/async_request_service.py', 'ctor:Request', 'status'),
    ('uk_management_bot/services/async_smart_dispatcher.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/async_smart_dispatcher.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/async_smart_dispatcher.py', 'attr:request', 'status'),
    ('uk_management_bot/services/inbound_alert.py', 'ctor:Request', 'status'),
    ('uk_management_bot/services/request_service.py', 'attr:request', 'completed_at'),
    ('uk_management_bot/services/request_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/request_service.py', 'attr:request', 'status'),
    ('uk_management_bot/services/request_service.py', 'ctor:Request', 'status'),
    ('uk_management_bot/services/shift_assignment_service.py', 'attr:shift', 'assigned_at'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:transfer', 'completed_at'),
    ('uk_management_bot/services/smart_dispatcher.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/smart_dispatcher.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/services/smart_dispatcher.py', 'attr:request', 'executor_id'),
}


def test_workflow_write_sites_match_baseline():
    actual = collect_write_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append("НОВЫЕ write-сайты workflow-полей (должны идти через "
                   "mutation-layer, PR2):\n" +
                   "\n".join(f"  {s!r}," for s in sorted(new_sites)))
    if gone_sites:
        msg.append("Исчезнувшие сайты (обновите baseline — переведены на layer?):\n" +
                   "\n".join(f"  {s!r}," for s in sorted(gone_sites)))
    assert not msg, "\n\n".join(msg)
