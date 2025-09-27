"""
Dual-Write Adapter for Request Service Migration
UK Management Bot - Request Management System

This adapter enables gradual migration from monolith to microservice
by writing to both systems during transition period.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import Request, RequestComment, RequestRating, RequestAssignment
from app.schemas.request import RequestCreate, RequestUpdate
from app.schemas import CommentCreate, RatingCreate
# from app.services.request_service import RequestService  # TODO: fix import
from app.core.config import settings

logger = logging.getLogger(__name__)


class DualWriteAdapter:
    """
    Adapter that writes to both monolith database and Request Service
    during migration period. Provides fallback mechanisms and consistency checks.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.request_service = RequestService(db_session)
        self.monolith_client = httpx.AsyncClient(
            base_url=settings.MONOLITH_API_URL,
            timeout=30.0,
            headers={"Authorization": f"Bearer {settings.INTERNAL_API_TOKEN}"}
        )
        self.migration_mode = settings.MIGRATION_MODE  # "dual", "microservice_only", "monolith_only"

    async def create_request(self, request_data: RequestCreate, creator_user_id: str) -> Dict[str, Any]:
        """
        Create request in both systems with consistency validation
        """
        microservice_result = None
        monolith_result = None
        errors = []

        try:
            # 1. Create in microservice first (primary)
            if self.migration_mode in ["dual", "microservice_only"]:
                logger.info(f"Creating request in microservice: {request_data.title}")
                microservice_result = await self.request_service.create_request(
                    request_data, creator_user_id
                )
                logger.info(f"Microservice created request: {microservice_result['request_number']}")

            # 2. Create in monolith (backup/fallback)
            if self.migration_mode in ["dual", "monolith_only"]:
                try:
                    monolith_payload = self._convert_to_monolith_format(request_data, creator_user_id)
                    response = await self.monolith_client.post(
                        "/api/internal/requests/create",
                        json=monolith_payload
                    )
                    response.raise_for_status()
                    monolith_result = response.json()
                    logger.info(f"Monolith created request: {monolith_result.get('request_number')}")

                except Exception as e:
                    logger.error(f"Failed to create in monolith: {e}")
                    errors.append(f"Monolith write failed: {e}")
                    if self.migration_mode == "monolith_only":
                        raise

            # 3. Validate consistency between systems
            if microservice_result and monolith_result:
                await self._validate_request_consistency(microservice_result, monolith_result)

            # Return primary result based on migration mode
            primary_result = microservice_result if microservice_result else monolith_result

            if errors:
                primary_result["migration_warnings"] = errors

            return primary_result

        except Exception as e:
            logger.error(f"Request creation failed: {e}")
            # Attempt cleanup if partial success
            await self._cleanup_partial_create(microservice_result, monolith_result)
            raise

    async def update_request(self, request_number: str, request_data: RequestUpdate,
                           updated_by: str) -> Dict[str, Any]:
        """
        Update request in both systems
        """
        microservice_result = None
        monolith_result = None
        errors = []

        try:
            # Update in microservice
            if self.migration_mode in ["dual", "microservice_only"]:
                microservice_result = await self.request_service.update_request(
                    request_number, request_data, updated_by
                )

            # Update in monolith
            if self.migration_mode in ["dual", "monolith_only"]:
                try:
                    monolith_payload = self._convert_update_to_monolith_format(request_data, updated_by)
                    response = await self.monolith_client.put(
                        f"/api/internal/requests/{request_number}",
                        json=monolith_payload
                    )
                    response.raise_for_status()
                    monolith_result = response.json()

                except Exception as e:
                    logger.error(f"Failed to update in monolith: {e}")
                    errors.append(f"Monolith update failed: {e}")
                    if self.migration_mode == "monolith_only":
                        raise

            primary_result = microservice_result if microservice_result else monolith_result
            if errors:
                primary_result["migration_warnings"] = errors

            return primary_result

        except Exception as e:
            logger.error(f"Request update failed: {e}")
            raise

    async def add_comment(self, request_number: str, comment_data: CommentCreate) -> Dict[str, Any]:
        """
        Add comment to both systems
        """
        microservice_result = None
        monolith_result = None
        errors = []

        try:
            # Add in microservice
            if self.migration_mode in ["dual", "microservice_only"]:
                microservice_result = await self.request_service.add_comment(
                    request_number, comment_data
                )

            # Add in monolith
            if self.migration_mode in ["dual", "monolith_only"]:
                try:
                    monolith_payload = {
                        "comment_text": comment_data.comment_text,
                        "author_user_id": comment_data.author_user_id,
                        "visibility": comment_data.visibility,
                        "is_internal": comment_data.is_internal
                    }
                    response = await self.monolith_client.post(
                        f"/api/internal/requests/{request_number}/comments",
                        json=monolith_payload
                    )
                    response.raise_for_status()
                    monolith_result = response.json()

                except Exception as e:
                    logger.error(f"Failed to add comment in monolith: {e}")
                    errors.append(f"Monolith comment failed: {e}")
                    if self.migration_mode == "monolith_only":
                        raise

            primary_result = microservice_result if microservice_result else monolith_result
            if errors:
                primary_result["migration_warnings"] = errors

            return primary_result

        except Exception as e:
            logger.error(f"Comment creation failed: {e}")
            raise

    async def update_status(self, request_number: str, new_status: str,
                          comment: Optional[str], user_id: str) -> Dict[str, Any]:
        """
        Update request status in both systems
        """
        microservice_result = None
        monolith_result = None
        errors = []

        try:
            # Update in microservice
            if self.migration_mode in ["dual", "microservice_only"]:
                microservice_result = await self.request_service.update_status(
                    request_number, new_status, comment, user_id
                )

            # Update in monolith
            if self.migration_mode in ["dual", "monolith_only"]:
                try:
                    monolith_payload = {
                        "status": new_status,
                        "comment": comment,
                        "user_id": user_id
                    }
                    response = await self.monolith_client.put(
                        f"/api/internal/requests/{request_number}/status",
                        json=monolith_payload
                    )
                    response.raise_for_status()
                    monolith_result = response.json()

                except Exception as e:
                    logger.error(f"Failed to update status in monolith: {e}")
                    errors.append(f"Monolith status update failed: {e}")
                    if self.migration_mode == "monolith_only":
                        raise

            primary_result = microservice_result if microservice_result else monolith_result
            if errors:
                primary_result["migration_warnings"] = errors

            return primary_result

        except Exception as e:
            logger.error(f"Status update failed: {e}")
            raise

    async def get_request(self, request_number: str) -> Optional[Dict[str, Any]]:
        """
        Get request with fallback between systems
        """
        try:
            # Try microservice first
            if self.migration_mode in ["dual", "microservice_only"]:
                result = await self.request_service.get_request(request_number)
                if result:
                    return result

            # Fallback to monolith
            if self.migration_mode in ["dual", "monolith_only"]:
                try:
                    response = await self.monolith_client.get(
                        f"/api/internal/requests/{request_number}"
                    )
                    response.raise_for_status()
                    return response.json()

                except Exception as e:
                    logger.error(f"Failed to get from monolith: {e}")
                    if self.migration_mode == "monolith_only":
                        raise

            return None

        except Exception as e:
            logger.error(f"Request retrieval failed: {e}")
            raise

    async def sync_request_from_monolith(self, request_number: str) -> bool:
        """
        Sync a specific request from monolith to microservice
        """
        try:
            # Get from monolith
            response = await self.monolith_client.get(
                f"/api/internal/requests/{request_number}"
            )
            response.raise_for_status()
            monolith_data = response.json()

            # Convert and create in microservice
            request_data = self._convert_from_monolith_format(monolith_data)
            await self.request_service.create_request(request_data, monolith_data["applicant_user_id"])

            logger.info(f"Successfully synced request {request_number} from monolith")
            return True

        except Exception as e:
            logger.error(f"Failed to sync request {request_number}: {e}")
            return False

    async def validate_data_consistency(self, request_number: str) -> Dict[str, Any]:
        """
        Validate data consistency between monolith and microservice
        """
        try:
            # Get from both systems
            microservice_data = None
            monolith_data = None

            try:
                microservice_data = await self.request_service.get_request(request_number)
            except Exception as e:
                logger.error(f"Failed to get from microservice: {e}")

            try:
                response = await self.monolith_client.get(
                    f"/api/internal/requests/{request_number}"
                )
                response.raise_for_status()
                monolith_data = response.json()
            except Exception as e:
                logger.error(f"Failed to get from monolith: {e}")

            # Compare data
            inconsistencies = []

            if microservice_data and monolith_data:
                # Check key fields
                key_fields = ["title", "description", "status", "priority", "category"]
                for field in key_fields:
                    micro_val = microservice_data.get(field)
                    mono_val = monolith_data.get(field)
                    if micro_val != mono_val:
                        inconsistencies.append({
                            "field": field,
                            "microservice_value": micro_val,
                            "monolith_value": mono_val
                        })

            return {
                "request_number": request_number,
                "microservice_exists": microservice_data is not None,
                "monolith_exists": monolith_data is not None,
                "inconsistencies": inconsistencies,
                "consistent": len(inconsistencies) == 0
            }

        except Exception as e:
            logger.error(f"Consistency validation failed: {e}")
            return {
                "request_number": request_number,
                "error": str(e),
                "consistent": False
            }

    def _convert_to_monolith_format(self, request_data: RequestCreate, creator_user_id: str) -> Dict[str, Any]:
        """Convert microservice format to monolith format"""
        return {
            "title": request_data.title,
            "description": request_data.description,
            "address": request_data.address,
            "apartment_number": request_data.apartment_number,
            "category": request_data.category,
            "priority": request_data.priority,
            "creator_user_id": creator_user_id,
            "contact_phone": request_data.contact_phone,
            "contact_name": request_data.contact_name,
            "is_emergency": request_data.is_emergency,
            "estimated_cost": float(request_data.estimated_cost) if request_data.estimated_cost else None,
            "preferred_time": request_data.preferred_time.isoformat() if request_data.preferred_time else None
        }

    def _convert_update_to_monolith_format(self, request_data: RequestUpdate, updated_by: str) -> Dict[str, Any]:
        """Convert update data to monolith format"""
        data = {"updated_by": updated_by}

        for field in ["title", "description", "address", "apartment_number", "category",
                     "priority", "contact_phone", "contact_name", "is_emergency"]:
            if hasattr(request_data, field) and getattr(request_data, field) is not None:
                data[field] = getattr(request_data, field)

        if request_data.estimated_cost is not None:
            data["estimated_cost"] = float(request_data.estimated_cost)

        if request_data.preferred_time is not None:
            data["preferred_time"] = request_data.preferred_time.isoformat()

        return data

    def _convert_from_monolith_format(self, monolith_data: Dict[str, Any]) -> RequestCreate:
        """Convert monolith format to microservice format"""
        return RequestCreate(
            title=monolith_data["title"],
            description=monolith_data["description"],
            address=monolith_data["address"],
            apartment_number=monolith_data.get("apartment_number"),
            category=monolith_data["category"],
            priority=monolith_data["priority"],
            contact_phone=monolith_data.get("contact_phone"),
            contact_name=monolith_data.get("contact_name"),
            is_emergency=monolith_data.get("is_emergency", False),
            estimated_cost=monolith_data.get("estimated_cost"),
            preferred_time=datetime.fromisoformat(monolith_data["preferred_time"])
                          if monolith_data.get("preferred_time") else None
        )

    async def _validate_request_consistency(self, microservice_result: Dict, monolith_result: Dict):
        """Validate that both systems created the same request"""
        micro_number = microservice_result.get("request_number")
        mono_number = monolith_result.get("request_number")

        if micro_number != mono_number:
            logger.warning(f"Request number mismatch: micro={micro_number}, mono={mono_number}")

    async def _cleanup_partial_create(self, microservice_result: Optional[Dict],
                                    monolith_result: Optional[Dict]):
        """Clean up partial creation in case of failure"""
        if microservice_result and not monolith_result:
            try:
                request_number = microservice_result["request_number"]
                await self.request_service.delete_request(request_number)
                logger.info(f"Cleaned up microservice request: {request_number}")
            except Exception as e:
                logger.error(f"Failed to cleanup microservice request: {e}")

    async def close(self):
        """Close HTTP client"""
        await self.monolith_client.aclose()