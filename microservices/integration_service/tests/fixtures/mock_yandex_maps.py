"""Mock Yandex Maps Geocoding API for testing.

Provides fake Yandex Maps API responses for testing fallback geocoding.
"""

from typing import Dict, Any, Optional, Tuple
import asyncio


class MockYandexMapsAPI:
    """Mock Yandex Maps Geocoding API."""

    def __init__(self):
        self.call_count = 0
        self.last_query: Optional[str] = None
        self.geocode_result: Optional[Tuple[float, float, str]] = None
        self.error: Optional[str] = None
        self.zero_results = False
        self.timeout = False

    def set_geocode_result(
        self,
        latitude: float,
        longitude: float,
        accuracy: str = "exact"
    ):
        """Configure successful geocoding result.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            accuracy: Geocoding accuracy (exact, range, near, etc.)
        """
        self.geocode_result = (latitude, longitude, accuracy)
        self.error = None
        self.zero_results = False
        self.timeout = False

    def set_error(self, error_type: str):
        """Configure error response.

        Args:
            error_type: Error type (SERVICE_UNAVAILABLE, etc.)
        """
        self.error = error_type
        self.geocode_result = None
        self.zero_results = False
        self.timeout = False

    def set_zero_results(self):
        """Configure ZERO_RESULTS response."""
        self.zero_results = True
        self.geocode_result = None
        self.error = None
        self.timeout = False

    def set_timeout(self):
        """Configure timeout."""
        self.timeout = True
        self.geocode_result = None
        self.error = None
        self.zero_results = False

    def reset(self):
        """Reset all mock state."""
        self.call_count = 0
        self.last_query = None
        self.geocode_result = None
        self.error = None
        self.zero_results = False
        self.timeout = False

    async def geocode(
        self,
        address: str,
        city: Optional[str] = None,
        country: str = "Uzbekistan"
    ) -> Tuple[float, float, str]:
        """Mock geocoding request.

        Args:
            address: Address to geocode
            city: Optional city
            country: Country

        Returns:
            Tuple of (latitude, longitude, accuracy)

        Raises:
            Exception: If error configured
        """
        self.call_count += 1

        # Build query
        query_parts = [address]
        if city:
            query_parts.append(city)
        query_parts.append(country)
        self.last_query = ", ".join(query_parts)

        # Simulate network delay
        await asyncio.sleep(0.01)

        # Check for timeout
        if self.timeout:
            raise asyncio.TimeoutError("Request timeout")

        # Check for error
        if self.error:
            raise Exception(f"Yandex Maps API Error: {self.error}")

        # Check for zero results
        if self.zero_results:
            raise Exception("ZERO_RESULTS")

        # Return configured result
        if self.geocode_result:
            return self.geocode_result

        # Default result
        return (41.311158, 69.279737, "exact")
