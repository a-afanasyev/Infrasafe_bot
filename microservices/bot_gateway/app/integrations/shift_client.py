"""
Bot Gateway Service - Shift Service Client
UK Management Bot

HTTP client for interacting with Shift Management Service.
Handles shift viewing, assignment, release, and availability management.
"""

from typing import Dict, Any, List, Optional
from datetime import date, datetime

from .base_client import BaseServiceClient
from app.core.config import settings


class ShiftServiceClient(BaseServiceClient):
    """
    Client for Shift Management Service.

    Provides methods for:
    - Viewing shifts (my shifts, available shifts, schedule)
    - Taking/releasing shifts
    - Managing availability
    - Viewing shift history
    """

    def __init__(self):
        super().__init__(
            base_url=settings.SHIFT_SERVICE_URL,
            service_name="shift-service",
        )

    # ===========================================
    # Shift Viewing
    # ===========================================

    async def get_my_shifts(
        self,
        token: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get user's assigned shifts.

        Args:
            token: JWT authentication token
            date_from: Start date filter (optional)
            date_to: End date filter (optional)
            status: Shift status filter (scheduled, completed, cancelled)
            limit: Maximum number of shifts to return
            offset: Pagination offset

        Returns:
            {
                "items": [
                    {
                        "id": "uuid",
                        "date": "2025-01-15",
                        "time_from": "09:00",
                        "time_to": "18:00",
                        "specialization": "plumber",
                        "status": "scheduled",
                        "building_ids": ["1", "2"],
                        ...
                    }
                ],
                "total": 10,
                "limit": 20,
                "offset": 0
            }
        """
        params = {"limit": limit, "offset": offset}

        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if status:
            params["status"] = status

        response = await self.get("/api/v1/shifts/my", params=params, token=token)
        return response.json()

    async def get_available_shifts(
        self,
        token: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        specialization: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get available shifts that user can take.

        Args:
            token: JWT authentication token
            date_from: Start date filter
            date_to: End date filter
            specialization: Filter by specialization
            limit: Maximum number of shifts
            offset: Pagination offset

        Returns:
            List of available shifts
        """
        params = {"limit": limit, "offset": offset}

        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()
        if specialization:
            params["specialization"] = specialization

        response = await self.get("/api/v1/shifts/available", params=params, token=token)
        return response.json()

    async def get_shift_by_id(self, shift_id: str, token: str) -> Dict[str, Any]:
        """
        Get detailed shift information by ID.

        Args:
            shift_id: Shift UUID
            token: JWT authentication token

        Returns:
            Detailed shift information
        """
        response = await self.get(f"/api/v1/shifts/{shift_id}", token=token)
        return response.json()

    async def get_schedule(
        self,
        token: str,
        date_from: date,
        date_to: date,
        executor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get shift schedule for date range.

        Args:
            token: JWT authentication token
            date_from: Start date
            date_to: End date
            executor_id: Filter by executor (optional, defaults to current user)

        Returns:
            Schedule data grouped by date
        """
        params = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

        if executor_id:
            params["executor_id"] = executor_id

        response = await self.get("/api/v1/shifts/schedule", params=params, token=token)
        return response.json()

    # ===========================================
    # Shift Assignment
    # ===========================================

    async def take_shift(self, shift_id: str, token: str) -> Dict[str, Any]:
        """
        Take an available shift.

        Args:
            shift_id: Shift UUID to take
            token: JWT authentication token

        Returns:
            Updated shift information
        """
        response = await self.post(f"/api/v1/shifts/{shift_id}/take", token=token)
        return response.json()

    async def release_shift(
        self, shift_id: str, reason: Optional[str], token: str
    ) -> Dict[str, Any]:
        """
        Release a previously taken shift.

        Args:
            shift_id: Shift UUID to release
            reason: Reason for releasing shift (optional)
            token: JWT authentication token

        Returns:
            Updated shift information
        """
        data = {}
        if reason:
            data["reason"] = reason

        response = await self.post(
            f"/api/v1/shifts/{shift_id}/release", json_data=data, token=token
        )
        return response.json()

    async def swap_shift(
        self, shift_id: str, target_executor_id: str, token: str
    ) -> Dict[str, Any]:
        """
        Request shift swap with another executor.

        Args:
            shift_id: Shift UUID to swap
            target_executor_id: Executor to swap with
            token: JWT authentication token

        Returns:
            Swap request information
        """
        data = {"target_executor_id": target_executor_id}

        response = await self.post(
            f"/api/v1/shifts/{shift_id}/swap", json_data=data, token=token
        )
        return response.json()

    # ===========================================
    # Availability Management
    # ===========================================

    async def get_my_availability(
        self, token: str, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get user's availability settings.

        Args:
            token: JWT authentication token
            date_from: Start date filter (optional)
            date_to: End date filter (optional)

        Returns:
            List of availability periods
        """
        params = {}
        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()

        response = await self.get("/api/v1/availability/my", params=params, token=token)
        return response.json()

    async def set_availability(
        self,
        date_from: date,
        date_to: date,
        is_available: bool,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        recurring: bool = False,
        days_of_week: Optional[List[int]] = None,
        token: str = None,
    ) -> Dict[str, Any]:
        """
        Set availability for date range.

        Args:
            date_from: Start date
            date_to: End date
            is_available: Available (True) or unavailable (False)
            time_from: Time from (HH:MM format, optional)
            time_to: Time to (HH:MM format, optional)
            recurring: Weekly recurring pattern
            days_of_week: Days of week (0=Monday, 6=Sunday) for recurring
            token: JWT authentication token

        Returns:
            Created availability record
        """
        data = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "is_available": is_available,
            "recurring": recurring,
        }

        if time_from:
            data["time_from"] = time_from
        if time_to:
            data["time_to"] = time_to
        if days_of_week:
            data["days_of_week"] = days_of_week

        response = await self.post("/api/v1/availability", json_data=data, token=token)
        return response.json()

    async def delete_availability(self, availability_id: str, token: str) -> Dict[str, Any]:
        """
        Delete availability setting.

        Args:
            availability_id: Availability record UUID
            token: JWT authentication token

        Returns:
            Success confirmation
        """
        response = await self.delete(f"/api/v1/availability/{availability_id}", token=token)
        return response.json()

    # ===========================================
    # Shift Statistics
    # ===========================================

    async def get_shift_statistics(
        self, token: str, month: Optional[int] = None, year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get shift statistics for user.

        Args:
            token: JWT authentication token
            month: Month filter (1-12)
            year: Year filter

        Returns:
            {
                "total_shifts": 20,
                "completed_shifts": 18,
                "cancelled_shifts": 2,
                "total_hours": 160.0,
                "specializations": {
                    "plumber": 10,
                    "electrician": 8,
                    ...
                }
            }
        """
        params = {}
        if month:
            params["month"] = month
        if year:
            params["year"] = year

        response = await self.get("/api/v1/shifts/statistics", params=params, token=token)
        return response.json()

    # ===========================================
    # Shift Templates
    # ===========================================

    async def get_shift_templates(self, token: str) -> Dict[str, Any]:
        """
        Get available shift templates.

        Returns:
            List of shift templates with schedules
        """
        response = await self.get("/api/v1/shifts/templates", token=token)
        return response.json()

    async def apply_template(
        self, template_id: str, date_from: date, date_to: date, token: str
    ) -> Dict[str, Any]:
        """
        Apply shift template to date range.

        Args:
            template_id: Template UUID
            date_from: Start date
            date_to: End date
            token: JWT authentication token

        Returns:
            List of created shifts
        """
        data = {
            "template_id": template_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }

        response = await self.post("/api/v1/shifts/apply-template", json_data=data, token=token)
        return response.json()
