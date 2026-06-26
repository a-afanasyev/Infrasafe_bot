"""Чтение оборудования: контроллеры, точки проезда (gates), шлагбаумы (§9.1).

Авторитетный scope точки въезда выводится из аутентифицированного контроллера и
его активного gate/barrier, а не из доверия payload. Все функции — read-only.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.equipment import EdgeController


def get_controller(db: Session, controller_id: int) -> EdgeController | None:
    """Контроллер по БД-id (или ``None``)."""
    return db.get(EdgeController, controller_id)


def gate_belongs_to_controller(
    db: Session, *, gate_id: int, controller_id: int
) -> bool:
    """Принадлежит ли gate данному контроллеру (§9.1)."""
    owns_gate = db.execute(
        text("SELECT 1 FROM access_gates WHERE id = :g AND controller_id = :c"),
        {"g": gate_id, "c": controller_id},
    ).scalar()
    return owns_gate is not None


def first_active_gate_for_controller(db: Session, controller_id: int) -> int | None:
    """id первого активного gate контроллера (по возрастанию id) либо ``None``."""
    return db.execute(
        text(
            "SELECT id FROM access_gates "
            "WHERE controller_id = :c AND is_active = true "
            "ORDER BY id LIMIT 1"
        ),
        {"c": controller_id},
    ).scalar()


def first_active_barrier_for_gate(db: Session, gate_id: int) -> int | None:
    """id первого активного шлагбаума gate (по возрастанию id) либо ``None``."""
    return db.execute(
        text(
            "SELECT id FROM access_barriers "
            "WHERE gate_id = :g AND is_active = true ORDER BY id LIMIT 1"
        ),
        {"g": gate_id},
    ).scalar()


def barrier_and_controller_for_event(
    db: Session, camera_event_id: int
) -> tuple[int | None, int | None]:
    """Авторитетный (barrier_id, controller_id) события по gate камеры (не из payload)."""
    row = db.execute(
        text(
            "SELECT b.id, b.controller_id "
            "FROM camera_events ce "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id AND b.is_active = true "
            "WHERE ce.id = :e ORDER BY b.id LIMIT 1"
        ),
        {"e": camera_event_id},
    ).first()
    return (row[0], row[1]) if row is not None else (None, None)


def active_controller_for_barrier(db: Session, barrier_id: int) -> int | None:
    """controller_id активного шлагбаума (или ``None``, если неактивен/нет)."""
    return db.execute(
        text(
            "SELECT controller_id FROM access_barriers "
            "WHERE id = :b AND is_active = true"
        ),
        {"b": barrier_id},
    ).scalar()
