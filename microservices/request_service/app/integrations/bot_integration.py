"""
Bot Integration Service for Request Service
UK Management Bot - Request Management System

This service handles integration with the Telegram bot,
providing API endpoints and webhook handlers for bot operations.
"""

import logging
from typing import Dict, Any, Optional, List
import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.dual_write_adapter import DualWriteAdapter
from app.schemas.request import RequestCreate, RequestUpdate
from app.schemas import CommentCreate, RatingCreate
from app.core.config import settings

logger = logging.getLogger(__name__)


class BotIntegrationService:
    """
    Service for integrating Request Service with Telegram Bot.
    Handles webhook calls from bot and provides simplified API for bot operations.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.dual_write_adapter = DualWriteAdapter(db_session)
        self.bot_client = httpx.AsyncClient(
            base_url=settings.BOT_SERVICE_URL,
            timeout=30.0,
            headers={"Authorization": f"Bearer {settings.INTERNAL_API_TOKEN}"}
        )

    async def create_request_from_bot(self, bot_request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create request from Telegram bot data
        Converts bot format to Request Service format
        """
        try:
            # Convert bot format to Request Service format
            request_data = self._convert_bot_to_request_format(bot_request_data)

            # Create request using dual-write adapter
            result = await self.dual_write_adapter.create_request(
                request_data,
                bot_request_data["user_id"]
            )

            # Send notification to bot about successful creation
            await self._notify_bot_request_created(result)

            return result

        except Exception as e:
            logger.error(f"Failed to create request from bot: {e}")
            # Notify bot about failure
            await self._notify_bot_request_failed(bot_request_data, str(e))
            raise HTTPException(status_code=500, detail=f"Request creation failed: {e}")

    async def update_request_from_bot(self, request_number: str,
                                    bot_update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update request from Telegram bot
        """
        try:
            # Convert bot format to update format
            request_update = self._convert_bot_to_update_format(bot_update_data)

            # Update using dual-write adapter
            result = await self.dual_write_adapter.update_request(
                request_number,
                request_update,
                bot_update_data["user_id"]
            )

            # Notify bot about update
            await self._notify_bot_request_updated(result)

            return result

        except Exception as e:
            logger.error(f"Failed to update request from bot: {e}")
            raise HTTPException(status_code=500, detail=f"Request update failed: {e}")

    async def add_comment_from_bot(self, request_number: str,
                                 bot_comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add comment from Telegram bot
        """
        try:
            # Convert bot format to comment format
            comment_data = CommentCreate(
                comment_text=bot_comment_data["message"],
                author_user_id=bot_comment_data["user_id"],
                visibility=bot_comment_data.get("visibility", "public"),
                is_internal=bot_comment_data.get("is_internal", False)
            )

            # Add comment using dual-write adapter
            result = await self.dual_write_adapter.add_comment(request_number, comment_data)

            # Notify interested parties via bot
            await self._notify_bot_comment_added(request_number, result)

            return result

        except Exception as e:
            logger.error(f"Failed to add comment from bot: {e}")
            raise HTTPException(status_code=500, detail=f"Comment creation failed: {e}")

    async def handle_bot_status_change(self, request_number: str,
                                     bot_status_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle status change from Telegram bot
        """
        try:
            new_status = bot_status_data["new_status"]
            comment = bot_status_data.get("comment")
            user_id = bot_status_data["user_id"]

            # Update status using dual-write adapter
            result = await self.dual_write_adapter.update_status(
                request_number, new_status, comment, user_id
            )

            # Notify all stakeholders via bot
            await self._notify_bot_status_changed(request_number, result)

            return result

        except Exception as e:
            logger.error(f"Failed to update status from bot: {e}")
            raise HTTPException(status_code=500, detail=f"Status update failed: {e}")

    async def handle_bot_assignment(self, request_number: str,
                                  assignment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle executor assignment from Telegram bot
        """
        try:
            # Call assignment service through dual-write adapter
            from app.services.assignment_service import AssignmentService
            assignment_service = AssignmentService(self.db_session)

            result = await assignment_service.assign_executor(
                request_number=request_number,
                assignment_data=assignment_data,
                assigned_by=assignment_data["assigned_by"]
            )

            # Notify bot about assignment
            await self._notify_bot_assignment_made(request_number, result)

            return result

        except Exception as e:
            logger.error(f"Failed to assign from bot: {e}")
            raise HTTPException(status_code=500, detail=f"Assignment failed: {e}")

    async def get_request_for_bot(self, request_number: str) -> Optional[Dict[str, Any]]:
        """
        Get request data formatted for Telegram bot
        """
        try:
            # Get request using dual-write adapter
            request_data = await self.dual_write_adapter.get_request(request_number)

            if not request_data:
                return None

            # Convert to bot format
            return self._convert_request_to_bot_format(request_data)

        except Exception as e:
            logger.error(f"Failed to get request for bot: {e}")
            raise HTTPException(status_code=500, detail=f"Request retrieval failed: {e}")

    async def search_requests_for_bot(self, search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search requests and format for Telegram bot
        """
        try:
            from app.services.search_service import SearchService
            search_service = SearchService(self.db_session)

            # Perform search
            results = await search_service.search_requests(
                text_query=search_params.get("text"),
                status_filter=search_params.get("status"),
                category_filter=search_params.get("category"),
                assigned_to=search_params.get("assigned_to"),
                limit=search_params.get("limit", 10),
                offset=search_params.get("offset", 0)
            )

            # Convert to bot format
            bot_results = []
            for request_data in results["requests"]:
                bot_results.append(self._convert_request_to_bot_format(request_data))

            return {
                "requests": bot_results,
                "total": results["total"],
                "has_more": results["total"] > (search_params.get("offset", 0) + len(bot_results))
            }

        except Exception as e:
            logger.error(f"Failed to search requests for bot: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    def _convert_bot_to_request_format(self, bot_data: Dict[str, Any]) -> RequestCreate:
        """Convert bot request format to Request Service format"""
        return RequestCreate(
            title=bot_data["title"],
            description=bot_data["description"],
            address=bot_data["address"],
            apartment_number=bot_data.get("apartment"),
            category=bot_data["category"],
            priority=bot_data.get("priority", "обычный"),
            contact_phone=bot_data.get("phone"),
            contact_name=bot_data.get("contact_name"),
            is_emergency=bot_data.get("is_emergency", False),
            estimated_cost=bot_data.get("estimated_cost"),
            preferred_time=bot_data.get("preferred_time")
        )

    def _convert_bot_to_update_format(self, bot_data: Dict[str, Any]) -> RequestUpdate:
        """Convert bot update format to Request Service format"""
        update_data = {}

        field_mapping = {
            "title": "title",
            "description": "description",
            "address": "address",
            "apartment": "apartment_number",
            "category": "category",
            "priority": "priority",
            "phone": "contact_phone",
            "contact_name": "contact_name",
            "is_emergency": "is_emergency",
            "estimated_cost": "estimated_cost",
            "preferred_time": "preferred_time"
        }

        for bot_field, service_field in field_mapping.items():
            if bot_field in bot_data:
                update_data[service_field] = bot_data[bot_field]

        return RequestUpdate(**update_data)

    def _convert_request_to_bot_format(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Request Service format to bot format"""
        return {
            "request_number": request_data["request_number"],
            "title": request_data["title"],
            "description": request_data["description"],
            "address": request_data["address"],
            "apartment": request_data.get("apartment_number"),
            "category": request_data["category"],
            "priority": request_data["priority"],
            "status": request_data["status"],
            "creator_user_id": request_data["applicant_user_id"],
            "executor_user_id": request_data.get("executor_user_id"),
            "phone": request_data.get("contact_phone"),
            "contact_name": request_data.get("contact_name"),
            "is_emergency": request_data.get("is_emergency", False),
            "estimated_cost": request_data.get("estimated_cost"),
            "created_at": request_data["created_at"],
            "updated_at": request_data["updated_at"],
            "preferred_time": request_data.get("preferred_time"),
            "comments_count": len(request_data.get("comments", [])),
            "rating": request_data.get("average_rating")
        }

    async def _notify_bot_request_created(self, request_data: Dict[str, Any]):
        """Notify bot about successful request creation"""
        try:
            notification_data = {
                "event": "request_created",
                "request_number": request_data["request_number"],
                "creator_user_id": request_data["applicant_user_id"],
                "title": request_data["title"],
                "category": request_data["category"],
                "priority": request_data["priority"]
            }

            await self.bot_client.post("/api/internal/notifications/request_created",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about request creation: {e}")

    async def _notify_bot_request_updated(self, request_data: Dict[str, Any]):
        """Notify bot about request update"""
        try:
            notification_data = {
                "event": "request_updated",
                "request_number": request_data["request_number"],
                "title": request_data["title"],
                "status": request_data["status"]
            }

            await self.bot_client.post("/api/internal/notifications/request_updated",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about request update: {e}")

    async def _notify_bot_comment_added(self, request_number: str, comment_data: Dict[str, Any]):
        """Notify bot about new comment"""
        try:
            notification_data = {
                "event": "comment_added",
                "request_number": request_number,
                "comment_id": comment_data["comment_id"],
                "author_user_id": comment_data["author_user_id"],
                "comment_text": comment_data["comment_text"][:100]  # Truncate for notification
            }

            await self.bot_client.post("/api/internal/notifications/comment_added",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about comment: {e}")

    async def _notify_bot_status_changed(self, request_number: str, request_data: Dict[str, Any]):
        """Notify bot about status change"""
        try:
            notification_data = {
                "event": "status_changed",
                "request_number": request_number,
                "new_status": request_data["status"],
                "executor_user_id": request_data.get("executor_user_id"),
                "creator_user_id": request_data["applicant_user_id"]
            }

            await self.bot_client.post("/api/internal/notifications/status_changed",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about status change: {e}")

    async def _notify_bot_assignment_made(self, request_number: str, assignment_data: Dict[str, Any]):
        """Notify bot about executor assignment"""
        try:
            notification_data = {
                "event": "assignment_made",
                "request_number": request_number,
                "assigned_to": assignment_data["assigned_to"],
                "assigned_by": assignment_data["assigned_by"],
                "assignment_reason": assignment_data.get("assignment_reason")
            }

            await self.bot_client.post("/api/internal/notifications/assignment_made",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about assignment: {e}")

    async def _notify_bot_request_failed(self, bot_request_data: Dict[str, Any], error_message: str):
        """Notify bot about failed request creation"""
        try:
            notification_data = {
                "event": "request_creation_failed",
                "user_id": bot_request_data["user_id"],
                "error": error_message,
                "original_data": bot_request_data
            }

            await self.bot_client.post("/api/internal/notifications/request_failed",
                                     json=notification_data)

        except Exception as e:
            logger.error(f"Failed to notify bot about request failure: {e}")

    async def close(self):
        """Close connections"""
        await self.dual_write_adapter.close()
        await self.bot_client.aclose()