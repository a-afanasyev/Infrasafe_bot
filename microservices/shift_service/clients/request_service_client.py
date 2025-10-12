# Request Service Client
# UK Management Bot - Shift Service

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from clients.base_client import BaseServiceClient, CircuitBreakerConfig
from config import settings

logger = logging.getLogger(__name__)


class RequestServiceClient(BaseServiceClient):
    """
    Client for Request Service API

    Provides methods to:
    - Get request assignments
    - Create/update assignment links
    - Query request status
    - Sync executor assignments
    """

    def __init__(self):
        # Get Request Service URL from config
        base_url = getattr(
            settings,
            "REQUEST_SERVICE_URL",
            "http://request-service:8000"
        )

        # Configure circuit breaker for Request Service
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,
            timeout_duration=60,
            success_threshold=2,
            request_timeout=10
        )

        super().__init__(
            service_name="Request Service",
            base_url=base_url,
            circuit_breaker_config=circuit_config
        )

    async def get_assignment_for_shift(
        self,
        shift_id: UUID,
        executor_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get request assignment for a specific shift and executor

        Args:
            shift_id: Shift ID
            executor_id: Executor ID

        Returns:
            Assignment data if found, None otherwise
        """
        try:
            endpoint = f"/api/v1/assignments/shift/{shift_id}/executor/{executor_id}"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(
                f"Could not get assignment from Request Service "
                f"(shift={shift_id}, executor={executor_id}): {e}"
            )
            return None

    async def create_assignment_link(
        self,
        shift_id: UUID,
        executor_id: UUID,
        assignment_id: UUID
    ) -> bool:
        """
        Create assignment link in Request Service

        Notifies Request Service about a shift assignment created in Shift Service

        Args:
            shift_id: Shift ID
            executor_id: Executor ID
            assignment_id: Assignment ID from Shift Service

        Returns:
            True if successful, False otherwise
        """
        try:
            endpoint = "/api/v1/assignments/sync"
            payload = {
                "shift_id": str(shift_id),
                "executor_id": str(executor_id),
                "shift_assignment_id": str(assignment_id),
                "source": "shift_service"
            }

            response = await self.post(endpoint, json=payload)
            logger.info(
                f"Created assignment link in Request Service: {assignment_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to create assignment link in Request Service "
                f"(assignment={assignment_id}): {e}"
            )
            return False

    async def get_requests_for_executor(
        self,
        executor_id: UUID,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all requests assigned to an executor

        Args:
            executor_id: Executor ID
            status: Optional status filter (e.g., "active", "completed")

        Returns:
            List of request objects
        """
        try:
            endpoint = f"/api/v1/requests/executor/{executor_id}"
            params = {}
            if status:
                params["status"] = status

            response = await self.get(endpoint, params=params)
            return response.get("requests", [])

        except Exception as e:
            logger.warning(
                f"Could not get requests for executor {executor_id}: {e}"
            )
            return []

    async def get_request_by_id(
        self,
        request_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get request by ID

        Args:
            request_id: Request UUID

        Returns:
            Request data if found, None otherwise
        """
        try:
            endpoint = f"/api/v1/requests/{request_id}"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(
                f"Could not get request {request_id}: {e}"
            )
            return None

    async def get_request_by_number(
        self,
        request_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get request by request number

        Args:
            request_number: Request number (e.g., "251002-001")

        Returns:
            Request data if found, None otherwise
        """
        try:
            endpoint = f"/api/v1/requests/by-number/{request_number}"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(
                f"Could not get request {request_number}: {e}"
            )
            return None

    async def update_request_status(
        self,
        request_number: str,
        status: str,
        updated_by: UUID
    ) -> bool:
        """
        Update request status

        Args:
            request_number: Request number
            status: New status
            updated_by: User ID making the update

        Returns:
            True if successful, False otherwise
        """
        try:
            endpoint = f"/api/v1/requests/{request_number}/status"
            payload = {
                "status": status,
                "updated_by": str(updated_by)
            }

            await self.patch(endpoint, json=payload)
            logger.info(f"Updated request {request_number} status to {status}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to update request {request_number} status: {e}"
            )
            return False

    async def get_executor_workload(
        self,
        executor_id: UUID
    ) -> Dict[str, Any]:
        """
        Get executor workload statistics

        Args:
            executor_id: Executor ID

        Returns:
            Workload statistics
        """
        try:
            endpoint = f"/api/v1/analytics/executor/{executor_id}/workload"
            response = await self.get(endpoint)
            return response

        except Exception as e:
            logger.warning(
                f"Could not get workload for executor {executor_id}: {e}"
            )
            return {
                "active_requests": 0,
                "total_requests": 0,
                "avg_completion_time": 0.0
            }

    async def sync_assignments_batch(
        self,
        assignments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Batch sync multiple assignments with Request Service

        Args:
            assignments: List of assignment data dicts

        Returns:
            Sync results with success/failure counts
        """
        try:
            endpoint = "/api/v1/assignments/sync/batch"
            payload = {
                "assignments": assignments,
                "source": "shift_service"
            }

            response = await self.post(endpoint, json=payload)
            logger.info(
                f"Batch synced {len(assignments)} assignments: "
                f"{response.get('synced', 0)} successful"
            )
            return response

        except Exception as e:
            logger.error(f"Failed to batch sync assignments: {e}")
            return {
                "synced": 0,
                "failed": len(assignments),
                "errors": [str(e)]
            }

    async def unassign_request(
        self,
        request_number: str,
        executor_id: UUID,
        reason: Optional[str] = None
    ) -> bool:
        """
        Unassign executor from request

        Args:
            request_number: Request number
            executor_id: Executor to unassign
            reason: Optional reason for unassignment

        Returns:
            True if successful, False otherwise
        """
        try:
            endpoint = f"/api/v1/requests/{request_number}/unassign"
            payload = {
                "executor_id": str(executor_id),
                "reason": reason
            }

            await self.post(endpoint, json=payload)
            logger.info(
                f"Unassigned executor {executor_id} from request {request_number}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to unassign request {request_number}: {e}"
            )
            return False
