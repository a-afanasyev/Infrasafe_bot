#!/usr/bin/env python3
"""
Скрипт для миграции старых назначений (Request.executor_id)
в новую систему (RequestAssignment)
"""

import sys
import os
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User


def migrate_legacy_assignments():
    """Миграция старых назначений в новую таблицу RequestAssignment"""

    db = next(get_db())

    try:
        # Находим все заявки с executor_id, но без записи в request_assignments
        legacy_requests = db.query(Request).filter(
            Request.executor_id.isnot(None)
        ).all()

        print(f"Найдено заявок со старыми назначениями: {len(legacy_requests)}")

        migrated = 0
        skipped = 0

        for request in legacy_requests:
            # Проверяем, есть ли уже активное назначение
            existing = db.query(RequestAssignment).filter(
                RequestAssignment.request_number == request.request_number,
                RequestAssignment.status == "active"
            ).first()

            if existing:
                print(f"  Пропущено {request.request_number}: уже есть активное назначение")
                skipped += 1
                continue

            # Создаем новое индивидуальное назначение
            assignment = RequestAssignment(
                request_number=request.request_number,
                assignment_type="individual",
                executor_id=request.executor_id,
                status="active",
                created_by=request.assigned_by if request.assigned_by else request.executor_id,
                created_at=request.assigned_at if request.assigned_at else request.created_at
            )

            db.add(assignment)

            # Обновляем поля заявки для совместимости
            request.assignment_type = "individual"
            request.assigned_at = request.assigned_at if request.assigned_at else datetime.now()
            request.assigned_by = request.assigned_by if request.assigned_by else request.executor_id

            print(f"  ✓ Мигрировано {request.request_number} → исполнитель ID {request.executor_id}")
            migrated += 1

        # Сохраняем изменения
        db.commit()

        print(f"\n✅ Миграция завершена!")
        print(f"  Мигрировано: {migrated}")
        print(f"  Пропущено: {skipped}")
        print(f"  Всего: {len(legacy_requests)}")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🔄 Начало миграции старых назначений...\n")
    migrate_legacy_assignments()
