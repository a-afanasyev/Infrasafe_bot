# Assignment Synchronization Task
# UK Management Bot - Shift Service
# Синхронизация shift assignments с request assignments

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftAssignment, ShiftStatus
from clients.request_service_client import RequestServiceClient
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AssignmentSynchronizationTask:
    """
    Задача синхронизации назначений между Shift Service и Request Service

    Обеспечивает согласованность данных о назначениях между сервисами:
    - Синхронизирует shift assignments с request assignments
    - Исправляет orphaned assignments (назначения без соответствующих заявок)
    - Создаёт недостающие связи между сервисами
    - Логирует все несоответствия для аудита

    Из монолита: services/shift_scheduler.py:545-600
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_name = "Assignment Synchronization"
        self.request_client = RequestServiceClient()
        logger.info(f"Initialized {self.task_name} task")

    async def execute(self) -> Dict[str, Any]:
        """
        Синхронизация shift assignments с request assignments

        Logic:
        1. Получить все активные shift assignments
        2. Проверить соответствие с request assignments через Request Service API
        3. Исправить несоответствия (orphaned assignments, missing links)
        4. Логировать результаты синхронизации

        Returns:
            Dict with synchronization results and statistics
        """
        try:
            start_time = utc_now()
            logger.info(f"Starting {self.task_name} task")

            # Get all active assignments from last 30 days
            cutoff_date = start_time - timedelta(days=30)
            stmt = select(ShiftAssignment).where(
                and_(
                    ShiftAssignment.is_active == True,
                    ShiftAssignment.assigned_at >= cutoff_date
                )
            )
            result = await self.db.execute(stmt)
            assignments = result.scalars().all()

            logger.info(f"Found {len(assignments)} active assignments to sync")

            # Synchronize with Request Service
            sync_results = await self.sync_with_request_service(assignments)

            # Fix orphaned assignments
            orphaned_fixed = await self.fix_orphaned_assignments(sync_results["orphaned"])

            # Create missing links
            links_created = await self.create_missing_links(sync_results["missing_links"])

            results = {
                "task": self.task_name,
                "started_at": start_time.isoformat(),
                "completed_at": utc_now().isoformat(),
                "status": "success",
                "total_assignments_checked": len(assignments),
                "synchronized_assignments": sync_results["synced_count"],
                "fixed_orphaned": orphaned_fixed,
                "created_missing_links": links_created,
                "discrepancies_found": sync_results["discrepancies"],
                "errors": sync_results["errors"]
            }

            logger.info(
                f"Completed {self.task_name}: "
                f"checked={len(assignments)}, "
                f"synced={sync_results['synced_count']}, "
                f"orphaned_fixed={orphaned_fixed}, "
                f"links_created={links_created}"
            )
            return results

        except Exception as e:
            logger.error(f"Error in {self.task_name}: {e}", exc_info=True)
            return {
                "task": self.task_name,
                "status": "error",
                "error": str(e),
                "completed_at": utc_now().isoformat()
            }

    async def sync_with_request_service(
        self,
        assignments: List[ShiftAssignment]
    ) -> Dict[str, Any]:
        """
        Синхронизация с Request Service

        Проверяет каждое назначение смены на соответствие с Request Service:
        - Запрашивает данные о назначениях из Request Service
        - Сравнивает executor_id и статусы
        - Выявляет orphaned и missing assignments

        Args:
            assignments: List of ShiftAssignment objects to sync

        Returns:
            Dict with sync results and discrepancies
        """
        try:
            synced_count = 0
            discrepancies = 0
            orphaned = []
            missing_links = []
            errors = []

            for assignment in assignments:
                try:
                    # Get shift details
                    stmt = select(Shift).where(Shift.id == assignment.shift_id)
                    result = await self.db.execute(stmt)
                    shift = result.scalar_one_or_none()

                    if not shift:
                        logger.warning(f"Shift {assignment.shift_id} not found for assignment {assignment.id}")
                        orphaned.append(assignment.id)
                        continue

                    # Check if Request Service has this assignment
                    # This would call Request Service API to verify executor assignment
                    request_assignment = await self.request_client.get_assignment_for_shift(
                        shift_id=assignment.shift_id,
                        executor_id=assignment.executor_id
                    )

                    if request_assignment is None:
                        # Assignment exists in Shift Service but not in Request Service
                        logger.warning(
                            f"Assignment {assignment.id} exists in Shift Service "
                            f"but not in Request Service (shift={assignment.shift_id})"
                        )
                        missing_links.append({
                            "assignment_id": assignment.id,
                            "shift_id": assignment.shift_id,
                            "executor_id": assignment.executor_id
                        })
                        discrepancies += 1
                    elif request_assignment["executor_id"] != str(assignment.executor_id):
                        # Executor mismatch
                        logger.warning(
                            f"Executor mismatch for assignment {assignment.id}: "
                            f"Shift Service has {assignment.executor_id}, "
                            f"Request Service has {request_assignment['executor_id']}"
                        )
                        discrepancies += 1
                    else:
                        # Assignment is in sync
                        synced_count += 1

                except Exception as e:
                    logger.error(f"Error syncing assignment {assignment.id}: {e}")
                    errors.append({
                        "assignment_id": str(assignment.id),
                        "error": str(e)
                    })

            return {
                "synced_count": synced_count,
                "discrepancies": discrepancies,
                "orphaned": orphaned,
                "missing_links": missing_links,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Error in sync_with_request_service: {e}", exc_info=True)
            return {
                "synced_count": 0,
                "discrepancies": 0,
                "orphaned": [],
                "missing_links": [],
                "errors": [{"error": str(e)}]
            }

    async def fix_orphaned_assignments(self, orphaned_ids: List[UUID]) -> int:
        """
        Исправление orphaned assignments

        Orphaned assignment - назначение, у которого:
        - Не существует смены (shift deleted)
        - Не существует исполнителя (executor deleted/deactivated)
        - Смена завершена, но assignment всё ещё активен

        Действия:
        - Деактивировать orphaned assignments
        - Логировать для аудита

        Args:
            orphaned_ids: List of orphaned assignment IDs

        Returns:
            Number of fixed assignments
        """
        try:
            if not orphaned_ids:
                return 0

            fixed_count = 0

            for assignment_id in orphaned_ids:
                try:
                    # Get assignment
                    stmt = select(ShiftAssignment).where(ShiftAssignment.id == assignment_id)
                    result = await self.db.execute(stmt)
                    assignment = result.scalar_one_or_none()

                    if not assignment:
                        continue

                    # Deactivate orphaned assignment
                    assignment.is_active = False
                    assignment.unassigned_at = utc_now()
                    assignment.unassignment_reason = "Auto-deactivated: orphaned assignment (shift not found)"

                    fixed_count += 1

                    logger.info(f"Deactivated orphaned assignment {assignment_id}")

                except Exception as e:
                    logger.error(f"Error fixing orphaned assignment {assignment_id}: {e}")

            await self.db.commit()

            logger.info(f"Fixed {fixed_count} orphaned assignments")
            return fixed_count

        except Exception as e:
            logger.error(f"Error in fix_orphaned_assignments: {e}", exc_info=True)
            await self.db.rollback()
            return 0

    async def create_missing_links(self, missing_links: List[Dict[str, Any]]) -> int:
        """
        Создание недостающих связей между Shift Service и Request Service

        Когда Shift Service имеет назначение, а Request Service - нет,
        уведомляем Request Service о назначении через API.

        Args:
            missing_links: List of assignments missing in Request Service

        Returns:
            Number of created links
        """
        try:
            if not missing_links:
                return 0

            created_count = 0

            for link in missing_links:
                try:
                    # Notify Request Service about this assignment
                    success = await self.request_client.create_assignment_link(
                        shift_id=link["shift_id"],
                        executor_id=link["executor_id"],
                        assignment_id=link["assignment_id"]
                    )

                    if success:
                        created_count += 1
                        logger.info(
                            f"Created missing link in Request Service: "
                            f"assignment={link['assignment_id']}, "
                            f"shift={link['shift_id']}, "
                            f"executor={link['executor_id']}"
                        )
                    else:
                        logger.warning(
                            f"Failed to create link in Request Service: {link['assignment_id']}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error creating link for assignment {link['assignment_id']}: {e}"
                    )

            logger.info(f"Created {created_count} missing links in Request Service")
            return created_count

        except Exception as e:
            logger.error(f"Error in create_missing_links: {e}", exc_info=True)
            return 0