"""Нормализация специализаций к единому словарю.

Поля хранились разнородно (JSON-список / CSV / скаляр) и содержали значения из
разных словарей: категорийный `elevator` рядом с `maintenance`, legacy
`electric`, `hvac`, `general`. Строгое сравнение в `rule_engine` не совпадало.

Канон и алиасы скопированы сюда ЛИТЕРАЛОМ, а не импортированы из модуля:
миграция обязана давать один и тот же результат независимо от того, как с тех
пор изменился код.

Revision ID: 010
Revises: 009
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANON = (
    "electrician", "plumber", "heating", "ventilation", "elevator",
    "cleaning", "security", "landscaping", "repair",
)
UNIVERSAL = "universal"

# Один legacy-токен может покрывать два современных (hvac).
ALIASES = {
    "electric": ("electrician",),
    "plumbing": ("plumber",),
    "patrol": ("security",),
    "hvac": ("heating", "ventilation"),
    "maintenance": ("elevator",),
    "general": ("repair",),
    "installation": ("repair",),
    "emergency": ("repair",),
    "other": ("repair",),
    # ключи КАТЕГОРИЙ в поле специализации — тот же класс, что elevator
    "electricity": ("electrician",),
    "internet": ("electrician",),
}
# Куда сворачиваем, когда место одно (скалярные group-поля и сторона «требуется»).
COLLAPSE = {"hvac": "heating"}


def _tokens(raw):
    """Разложить разнородное хранение в список сырых токенов."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(s).strip() for s in raw if str(s).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if str(s).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    return [p.strip() for p in text.split(",") if p.strip()]


def _normalize(token: str, *, collapse: bool) -> list[str]:
    low = token.strip().lower()
    if not low:
        return []
    if low in CANON:
        return [low]
    if low == UNIVERSAL:
        return [UNIVERSAL]
    targets = ALIASES.get(low)
    if targets is None:
        return []
    if collapse and low in COLLAPSE:
        return [COLLAPSE[low]]
    return list(targets)


def _normalize_list(raw, *, collapse: bool) -> list[str]:
    out: list[str] = []
    for token in _tokens(raw):
        for value in _normalize(token, collapse=collapse):
            if value not in out:
                out.append(value)
    return out


def upgrade() -> None:
    bind = op.get_bind()
    unresolved: list[str] = []

    # ── users.specialization: сторона «умею» — hvac разворачиваем в оба ──
    rows = bind.execute(sa.text(
        "SELECT id, specialization, roles FROM users "
        "WHERE specialization IS NOT NULL AND specialization <> ''"
    )).fetchall()
    for user_id, raw, roles in rows:
        normalized = _normalize_list(raw, collapse=False)
        if not normalized and "executor" in (roles or ""):
            # Обнулить специализацию исполнителя нельзя молча: она входит в
            # предикат доступа (services/request_access.py), и человек потерял
            # бы групповую видимость заявок, которые раньше мог взять.
            unresolved.append(f"users[{user_id}]={raw!r}")
            continue
        value = json.dumps(normalized, ensure_ascii=False) if normalized else None
        bind.execute(
            sa.text("UPDATE users SET specialization = :v WHERE id = :i"),
            {"v": value, "i": user_id},
        )

    # ── смены и шаблоны: сторона «требуется» — одно значение на токен ──
    #    Пустой результат → NULL, а НЕ [] : пустой список читается как
    #    «смена не принимает ничего», ровно тот failure-mode, из-за которого
    #    заявка не находила исполнителя.
    for table, column in (
        ("shifts", "specialization_focus"),
        ("shift_templates", "required_specializations"),
    ):
        rows = bind.execute(sa.text(
            f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL"
        )).fetchall()
        for row_id, raw in rows:
            normalized = _normalize_list(raw, collapse=True)
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :i").bindparams(
                    sa.bindparam("v", type_=sa.JSON())),
                {"v": normalized or None, "i": row_id},
            )

    # ── group-поля: скаляры String(100), множество туда не помещается ──
    #    Значение вычислялось из категории своей заявки, поэтому его и
    #    пересчитываем — двусмысленность hvac при этом не возникает.
    unresolved += _normalize_group_columns(bind)

    if unresolved:
        raise RuntimeError(
            "Миграция 010 остановлена: значения не резолвятся в канон, а обнулить\n"
            "их нельзя без потери доступа к заявкам. Разберите вручную:\n  "
            + "\n  ".join(unresolved)
        )


def _normalize_group_columns(bind) -> list[str]:
    """requests.assigned_group и request_assignments.group_specialization.

    Returns: список нерезолвимых значений (пустой — всё в порядке).
    """
    unresolved: list[str] = []

    rows = bind.execute(sa.text(
        "SELECT request_number, assigned_group FROM requests "
        "WHERE assigned_group IS NOT NULL AND assigned_group <> ''"
    )).fetchall()
    for number, raw in rows:
        normalized = _normalize_list(raw, collapse=True)
        if not normalized:
            unresolved.append(f"requests[{number}]={raw!r}")
            continue
        bind.execute(
            sa.text("UPDATE requests SET assigned_group = :v WHERE request_number = :n"),
            {"v": normalized[0], "n": number},
        )

    rows = bind.execute(sa.text(
        "SELECT id, group_specialization, status FROM request_assignments "
        "WHERE group_specialization IS NOT NULL AND group_specialization <> ''"
    )).fetchall()
    for row_id, raw, status in rows:
        normalized = _normalize_list(raw, collapse=True)
        if not normalized:
            # У АКТИВНОГО назначения обнулять нельзя: группа входит в предикат
            # доступа (services/request_access.py), и исполнитель потерял бы
            # заявку, которую ведёт. Останавливаемся и разбираем руками.
            if status == "active":
                unresolved.append(f"request_assignments[{row_id}]={raw!r} (active)")
            continue
        bind.execute(
            sa.text("UPDATE request_assignments SET group_specialization = :v WHERE id = :i"),
            {"v": normalized[0], "i": row_id},
        )

    return unresolved


def downgrade() -> None:
    """No-op: обратного отображения нет.

    `hvac` разворачивался в два значения, `maintenance`/`general`/`installation`
    схлопывались в один — восстановить исходные токены нельзя, а гадать хуже,
    чем оставить канон.
    """
