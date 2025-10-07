"""
Request Service Client
UK Management Bot - Bot Gateway Service

Client for Request Service communication.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.core.config import settings
from .base_client import BaseServiceClient

logger = logging.getLogger(__name__)


class RequestServiceClient(BaseServiceClient):
    """
    Request Service Client

    Handles request management operations:
    - Create, update, delete requests
    - Assign executors
    - Change request status
    - Get request history
    - Search and filter requests
    """

    def __init__(self):
        super().__init__(
            base_url=settings.REQUEST_SERVICE_URL,
            service_name="RequestService"
        )

    async def create_request(
        self,
        data: Dict[str, Any],
        token: str
    ) -> Dict[str, Any]:
        """
        Create new request.

        Args:
            data: Request data (building_id, apartment, description, etc.)
            token: JWT access token

        Returns:
            Created request with request_number
        """
        response = await self.post(
            endpoint="/api/v1/requests",
            data=data,
            token=token
        )
        return response.json()

    async def get_request(
        self,
        request_number: str,
        token: str
    ) -> Dict[str, Any]:
        """
        Get request by request_number.

        Args:
            request_number: Request number (YYMMDD-NNN format)
            token: JWT access token

        Returns:
            Request information
        """
        response = await self.get(
            endpoint=f"/api/v1/requests/{request_number}",
            token=token
        )
        return response.json()

    async def get_my_requests(
        self,
        token: str,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get current user's requests.

        Args:
            token: JWT access token
            status: Filter by status (optional)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            {"requests": [...], "total": N}
        """
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await self.get(
            endpoint="/api/v1/requests/my",
            params=params,
            token=token
        )
        return response.json()

    async def update_request(
        self,
        request_number: str,
        data: Dict[str, Any],
        token: str
    ) -> Dict[str, Any]:
        """
        Update request.

        Args:
            request_number: Request number
            data: Update data
            token: JWT access token

        Returns:
            Updated request
        """
        response = await self.put(
            endpoint=f"/api/v1/requests/{request_number}",
            data=data,
            token=token
        )
        return response.json()

    async def change_status(
        self,
        request_number: str,
        new_status: str,
        comment: Optional[str] = None,
        token: str = None
    ) -> Dict[str, Any]:
        """
        Change request status.

        Args:
            request_number: Request number
            new_status: New status
            comment: Optional comment
            token: JWT access token

        Returns:
            Updated request
        """
        data = {"status": new_status}
        if comment:
            data["comment"] = comment

        response = await self.patch(
            endpoint=f"/api/v1/requests/{request_number}/status",
            data=data,
            token=token
        )
        return response.json()

    async def assign_executor(
        self,
        request_number: str,
        executor_id: UUID,
        token: str
    ) -> Dict[str, Any]:
        """
        Assign executor to request.

        Args:
            request_number: Request number
            executor_id: Executor user ID
            token: JWT access token

        Returns:
            Updated request with executor assignment
        """
        response = await self.post(
            endpoint=f"/api/v1/requests/{request_number}/assign",
            data={"executor_id": str(executor_id)},
            token=token
        )
        return response.json()

    async def add_comment(
        self,
        request_number: str,
        comment_text: str,
        token: str
    ) -> Dict[str, Any]:
        """
        Add comment to request.

        Args:
            request_number: Request number
            comment_text: Comment text
            token: JWT access token

        Returns:
            Created comment
        """
        response = await self.post(
            endpoint=f"/api/v1/requests/{request_number}/comments",
            data={"text": comment_text},
            token=token
        )
        return response.json()

    async def get_comments(
        self,
        request_number: str,
        token: str
    ) -> List[Dict[str, Any]]:
        """
        Get request comments.

        Args:
            request_number: Request number
            token: JWT access token

        Returns:
            List of comments
        """
        response = await self.get(
            endpoint=f"/api/v1/requests/{request_number}/comments",
            token=token
        )
        return response.json()

    async def search_requests(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        token: str = None
    ) -> Dict[str, Any]:
        """
        Search requests.

        Args:
            query: Search query
            filters: Additional filters (status, building_id, etc.)
            token: JWT access token

        Returns:
            Search results
        """
        params = {"q": query}
        if filters:
            params.update(filters)

        response = await self.get(
            endpoint="/api/v1/requests/search",
            params=params,
            token=token
        )
        return response.json()

    async def get_request_statistics(
        self,
        token: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get request statistics.

        Args:
            token: JWT access token
            start_date: Start date (ISO format)
            end_date: End date (ISO format)

        Returns:
            Statistics data
        """
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = await self.get(
            endpoint="/api/v1/requests/statistics",
            params=params,
            token=token
        )
        return response.json()


# Global Request Service client instance
request_client = RequestServiceClient()
