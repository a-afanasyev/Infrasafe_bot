# User Service Client
# UK Management Bot - Shift Service

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from clients.base_client import BaseServiceClient, CircuitBreakerConfig
from config import settings

logger = logging.getLogger(__name__)


class UserServiceClient(BaseServiceClient):
    """
    Client for User Service API

    Provides methods to:
    - Get user profiles
    - Check executor availability
    - Get executor specializations
    - Validate user permissions
    """

    def __init__(self):
        # Get User Service URL from config
        base_url = getattr(
            settings,
            "USER_SERVICE_URL",
            "http://user-service:8000"
        )

        # Configure circuit breaker for User Service
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,
            timeout_duration=60,
            success_threshold=2,
            request_timeout=10
        )

        super().__init__(
            service_name="User Service",
            base_url=base_url,
            circuit_breaker_config=circuit_config
        )

    async def get_user_profile(
        self,
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get user profile by ID

        Args:
            user_id: User ID

        Returns:
            User profile data if found, None otherwise
        """
        try:
            endpoint = f"/api/v1/users/{user_id}"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(f"Could not get user profile for {user_id}: {e}")
            return None

    async def get_executor_profile(
        self,
        executor_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get executor profile with specialization details

        Args:
            executor_id: Executor ID

        Returns:
            Executor profile with specializations, availability, rating
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(f"Could not get executor profile for {executor_id}: {e}")
            return None

    async def check_executor_availability(
        self,
        executor_id: UUID,
        start_time: str,
        end_time: str
    ) -> bool:
        """
        Check if executor is available during a time period

        Args:
            executor_id: Executor ID
            start_time: Start time (ISO format)
            end_time: End time (ISO format)

        Returns:
            True if available, False otherwise
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}/availability"
            params = {
                "start_time": start_time,
                "end_time": end_time
            }

            response = await self.get(endpoint, params=params)
            return response.get("available", False)

        except Exception as e:
            logger.warning(
                f"Could not check availability for executor {executor_id}: {e}"
            )
            return False

    async def get_executors_by_specialization(
        self,
        specialization: str,
        available_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get executors with a specific specialization

        Args:
            specialization: Specialization type
            available_only: Only return available executors

        Returns:
            List of executor profiles
        """
        try:
            endpoint = "/api/v1/executors/search"
            params = {
                "specialization": specialization,
                "available": available_only
            }

            response = await self.get(endpoint, params=params)
            return response.get("executors", [])

        except Exception as e:
            logger.warning(
                f"Could not get executors for specialization {specialization}: {e}"
            )
            return []

    async def get_executor_rating(
        self,
        executor_id: UUID
    ) -> float:
        """
        Get executor's average rating

        Args:
            executor_id: Executor ID

        Returns:
            Average rating (0.0-5.0)
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}/rating"
            response = await self.get(endpoint)
            return response.get("average_rating", 0.0)

        except Exception as e:
            logger.warning(f"Could not get rating for executor {executor_id}: {e}")
            return 0.0

    async def validate_user_role(
        self,
        user_id: UUID,
        required_role: str
    ) -> bool:
        """
        Validate if user has required role

        Args:
            user_id: User ID
            required_role: Required role (e.g., "executor", "manager")

        Returns:
            True if user has role, False otherwise
        """
        try:
            endpoint = f"/api/v1/users/{user_id}/roles"
            response = await self.get(endpoint)
            roles = response.get("roles", [])
            return required_role in roles

        except Exception as e:
            logger.warning(f"Could not validate role for user {user_id}: {e}")
            return False

    async def get_executors_batch(
        self,
        executor_ids: List[UUID]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get multiple executor profiles in one request

        Args:
            executor_ids: List of executor IDs

        Returns:
            Dict mapping executor_id to profile data
        """
        try:
            endpoint = "/api/v1/executors/batch"
            payload = {
                "executor_ids": [str(id) for id in executor_ids]
            }

            response = await self.post(endpoint, json=payload)
            return response.get("executors", {})

        except Exception as e:
            logger.warning(f"Could not get batch executors: {e}")
            return {}

    async def update_executor_status(
        self,
        executor_id: UUID,
        status: str
    ) -> bool:
        """
        Update executor status (available, busy, offline)

        Args:
            executor_id: Executor ID
            status: New status

        Returns:
            True if successful, False otherwise
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}/status"
            payload = {"status": status}

            await self.patch(endpoint, json=payload)
            logger.info(f"Updated executor {executor_id} status to {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update executor {executor_id} status: {e}")
            return False

    async def get_executor_schedule(
        self,
        executor_id: UUID,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Get executor's schedule for a date range

        Args:
            executor_id: Executor ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of scheduled time slots
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}/schedule"
            params = {
                "start_date": start_date,
                "end_date": end_date
            }

            response = await self.get(endpoint, params=params)
            return response.get("schedule", [])

        except Exception as e:
            logger.warning(
                f"Could not get schedule for executor {executor_id}: {e}"
            )
            return []

    async def record_executor_performance(
        self,
        executor_id: UUID,
        shift_id: UUID,
        performance_data: Dict[str, Any]
    ) -> bool:
        """
        Record executor performance metrics from a shift

        Args:
            executor_id: Executor ID
            shift_id: Shift ID
            performance_data: Performance metrics

        Returns:
            True if successful, False otherwise
        """
        try:
            endpoint = f"/api/v1/executors/{executor_id}/performance"
            payload = {
                "shift_id": str(shift_id),
                **performance_data
            }

            await self.post(endpoint, json=payload)
            logger.info(
                f"Recorded performance for executor {executor_id}, shift {shift_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to record performance for executor {executor_id}: {e}"
            )
            return False
