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
# BASELINE — ALLOWLIST-ЯДРО (достигнуто в PR2d, 2026-06-11). После PR2a-2d ВСЕ
# workflow-переходы заявки идут через канонический writer run_command
# (utils/request_workflow + services/workflow_runner; динамический setattr —
# AST-невидим). Здесь остаётся только ЯДРО-allowlist:
#
#   1. CREATE-фабрика: ctor:Request/RequestModel со status — создание заявки
#      (status="Новая") в callcenter/requests/request_service/async_request_
#      service/inbound_alert. Это не переход, а рождение записи.
#   2. ASSIGNMENT-mutation-layer: assignment_service / async_assignment_service —
#      единственный санкционированный writer полей назначения (executor_id/
#      assigned_*/RequestAssignment). Диспетчер/оптимизатор/admin-auto-assign/
#      delete_employee (PR2d) теперь пишут ТОЛЬКО через него (assign_to_*/
#      reassign_executor); сам сервис — allowlist. attr:active executor_id —
#      reassign_executor (обновление активного RequestAssignment in place).
#   3. SHIFT-машина (вне scope кластера #1): Shift/ShiftTransfer/ShiftAssignment
#      (completed_at/assigned_at) + shift_assignment_service/shift_transfer_
#      service + api/shifts transfer.assigned_at — отдельная машина статусов
#      смен, одноимённые поля (шум-инвариант).
#   4. ONE-OFF migration: fix_manager_confirmed_legacy.py (план, риск №30).
#   5. WORKFLOW-RUNNER claim-домен-оп (FEAT-группы): claim_group_assignment в
#      workflow_runner конвертирует активное group-назначение в individual
#      in-place (executor_id := взявший) через UPDATE...values/update. Это
#      САМ канонический run_command-слой (а не сырой обход) — взятие из пула
#      идёт под FOR UPDATE-локом + rowcount-guard, как и прочие domain-ops.
#
# Любой НОВЫЙ кортеж = либо новый сырой writer (должен идти через run_command/
# assignment_service), либо осознанное расширение ядра с обоснованием здесь.
# ---------------------------------------------------------------------------

BASELINE: set[tuple[str, str, str]] = {
    # 1. CREATE-фабрика (создание заявки, status="Новая")
    ('uk_management_bot/api/callcenter/router.py', 'ctor:Request', 'status'),
    ('uk_management_bot/api/requests/router.py', 'ctor:RequestModel', 'status'),
    ('uk_management_bot/handlers/requests.py', 'ctor:Request', 'status'),
    ('uk_management_bot/services/request_service.py', 'ctor:Request', 'status'),
    ('uk_management_bot/services/inbound_alert.py', 'ctor:Request', 'status'),
    # 2. ASSIGNMENT mutation-layer (allowlist): единственный writer назначений.
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assigned_group'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/services/assignment_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/assignment_service.py', 'attr:active', 'executor_id'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assigned_group'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'assignment_type'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/async_assignment_service.py', 'attr:active', 'executor_id'),
    # 3. SHIFT-машина (вне scope; одноимённые поля Shift/ShiftTransfer)
    ('uk_management_bot/api/shifts/router.py', 'attr:transfer', 'assigned_at'),
    ('uk_management_bot/database/models/shift_assignment.py', 'attr:self', 'completed_at'),
    ('uk_management_bot/database/models/shift_transfer.py', 'attr:self', 'assigned_at'),
    ('uk_management_bot/database/models/shift_transfer.py', 'attr:self', 'completed_at'),
    ('uk_management_bot/services/shift_assignment_service.py', 'attr:shift', 'assigned_at'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'assigned_at'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'assigned_by'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:request', 'executor_id'),
    ('uk_management_bot/services/shift_transfer_service.py', 'attr:transfer', 'completed_at'),
    # 4. ONE-OFF migration-скрипт (план, риск №30)
    # 5. WORKFLOW-RUNNER claim-домен-оп (FEAT-группы): взятие group→individual
    ('uk_management_bot/services/workflow_runner.py', 'update()', 'assignment_type'),
    ('uk_management_bot/services/workflow_runner.py', 'update()', 'executor_id'),
    ('uk_management_bot/services/workflow_runner.py', 'values()', 'assignment_type'),
    ('uk_management_bot/services/workflow_runner.py', 'values()', 'executor_id'),
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
