# Transfer Monitoring Background Task
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.transfers import ShiftTransfer, TransferStatus
from models.shifts import Shift
from utils.datetime_utils import utc_now
from config import settings

logger = logging.getLogger(__name__)


class TransferMonitoringTask:
    """
    Background task for monitoring pending shift transfers and handling automation
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = settings

    async def execute(self) -> Dict[str, Any]:
        """Execute the transfer monitoring task"""
        logger.info("Starting transfer monitoring task")

        result = {
            "transfers_processed": 0,
            "overdue_transfers": 0,
            "auto_completions": 0,
            "notifications_sent": 0,
            "errors": [],
            "execution_time": 0
        }

        start_time = utc_now()

        try:
            # Find pending transfers that need attention
            pending_transfers = await self._find_pending_transfers()
            result["transfers_processed"] = len(pending_transfers)

            for transfer in pending_transfers:
                try:
                    if transfer.is_overdue:
                        result["overdue_transfers"] += 1
                        await self._handle_overdue_transfer(transfer)

                    if transfer.is_pending_assignment:
                        # Try to find replacement automatically
                        if await self._attempt_auto_replacement(transfer):
                            result["auto_completions"] += 1

                except Exception as e:
                    error_msg = f"Failed to process transfer {transfer.id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Transfer monitoring task failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        finally:
            result["execution_time"] = (utc_now() - start_time).total_seconds()
            logger.info(f"Transfer monitoring completed: {result}")

        return result

    async def _find_pending_transfers(self) -> List[ShiftTransfer]:
        """Find transfers that need monitoring"""
        try:
            stmt = (
                select(ShiftTransfer)
                .where(
                    ShiftTransfer.status.in_([
                        TransferStatus.PENDING,
                        TransferStatus.APPROVED
                    ])
                )
                .order_by(ShiftTransfer.requested_at)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Failed to find pending transfers: {e}")
            return []

    async def _handle_overdue_transfer(self, transfer: ShiftTransfer):
        """Handle overdue transfer that needs immediate attention"""
        try:
            logger.warning(
                f"Transfer {transfer.id} is overdue - deadline: {transfer.assignment_deadline}"
            )

            # Check how overdue it is
            now = utc_now()
            hours_overdue = (now - transfer.assignment_deadline).total_seconds() / 3600

            # Update notifications
            notifications = transfer.notifications_sent or {}

            if hours_overdue >= 24 and "escalated_24h" not in notifications:
                # 24h overdue - escalate to senior management
                await self._escalate_transfer(transfer, level="high")
                notifications["escalated_24h"] = now.isoformat()

            elif hours_overdue >= 12 and "escalated_12h" not in notifications:
                # 12h overdue - escalate to management
                await self._escalate_transfer(transfer, level="medium")
                notifications["escalated_12h"] = now.isoformat()

            elif hours_overdue >= 1 and "overdue_warning" not in notifications:
                # Just became overdue - warning notification
                await self._escalate_transfer(transfer, level="low")
                notifications["overdue_warning"] = now.isoformat()

            transfer.notifications_sent = notifications
            await self.db.commit()

        except Exception as e:
            logger.error(f"Failed to handle overdue transfer {transfer.id}: {e}")

    async def _attempt_auto_replacement(self, transfer: ShiftTransfer) -> bool:
        """
        Attempt to automatically find replacement for transfer

        Uses TransferService to find suggestions
        If high-confidence match found, auto-assign
        """
        try:
            logger.info(f"Attempting auto-replacement for transfer {transfer.id}")

            # Import here to avoid circular dependency
            from services.transfer_service import TransferService

            transfer_service = TransferService(self.db)

            # Get replacement suggestions
            suggestions = await transfer_service.suggest_replacements(transfer.id, limit=5)

            if not suggestions:
                logger.info(f"No replacement suggestions found for transfer {transfer.id}")
                return False

            # Check if we have a high-confidence match
            # (In production, would use AI scoring threshold)
            if len(suggestions) > 0:
                top_suggestion = suggestions[0]
                confidence_threshold = 0.85

                if top_suggestion.get("confidence", 0) >= confidence_threshold:
                    # Auto-assign with high confidence
                    executor_id = UUID(top_suggestion["executor_id"])

                    logger.info(
                        f"Auto-assigning transfer {transfer.id} to executor {executor_id} "
                        f"(confidence: {top_suggestion['confidence']})"
                    )

                    await transfer_service.assign_replacement(
                        transfer.id,
                        executor_id,
                        self.settings.system_user_uuid
                    )

                    return True

                else:
                    logger.info(
                        f"No high-confidence match for transfer {transfer.id} "
                        f"(best: {top_suggestion.get('confidence', 0)})"
                    )

            return False

        except Exception as e:
            logger.error(f"Failed auto-replacement for transfer {transfer.id}: {e}")
            return False

    async def _escalate_transfer(self, transfer: ShiftTransfer, level: str = "medium"):
        """
        Escalate overdue transfer to management

        Args:
            transfer: ShiftTransfer to escalate
            level: Escalation level (low/medium/high)
        """
        try:
            logger.warning(
                f"Escalating transfer {transfer.id} to {level} level - "
                f"shift: {transfer.shift_id}, deadline: {transfer.assignment_deadline}"
            )

            # Build escalation message
            escalation_data = {
                "transfer_id": str(transfer.id),
                "shift_id": str(transfer.shift_id),
                "from_executor": str(transfer.from_executor_id),
                "reason": transfer.reason,
                "deadline": transfer.assignment_deadline.isoformat() if transfer.assignment_deadline else None,
                "hours_overdue": (utc_now() - transfer.assignment_deadline).total_seconds() / 3600 if transfer.assignment_deadline else 0,
                "level": level
            }

            # TODO: Send notification to managers via Notification Service
            # For now, just log the escalation
            logger.warning(f"ESCALATION [{level.upper()}]: {escalation_data}")

            # In production, would call:
            # await notification_service.send_escalation(
            #     type="transfer_overdue",
            #     level=level,
            #     data=escalation_data,
            #     recipients=["managers", "shift_coordinators"]
            # )

        except Exception as e:
            logger.error(f"Failed to escalate transfer {transfer.id}: {e}")
