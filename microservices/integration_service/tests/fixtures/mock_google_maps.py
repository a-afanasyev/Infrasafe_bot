"""Mock Google Maps Geocoding API for testing.

Provides fake Google Maps API responses for testing GeocodingService
without making actual API calls.
"""

from typing import Dict, Any, Optional, Tuple, List
import asyncio


class MockGoogleMapsAPI:
    """Mock Google Maps Geocoding API."""

    def __init__(self):
        self.call_count = 0
        self.last_query: Optional[str] = None
        self.geocode_result: Optional[Tuple[float, float, str]] = None
        self.reverse_geocode_result: Optional[Dict[str, str]] = None
        self.error: Optional[str] = None
        self.zero_results = False
        self.timeout = False
        self.concurrent_requests = 0
        self.max_concurrent_requests = 0
        self.selective_failures: List[int] = []

    def set_geocode_result(
        self,
        latitude: float,
        longitude: float,
        accuracy: str = "ROOFTOP"
    ):
        """Configure successful geocoding result.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            accuracy: Geocoding accuracy (ROOFTOP, RANGE_INTERPOLATED, etc.)
        """
        self.geocode_result = (latitude, longitude, accuracy)
        self.error = None
        self.zero_results = False
        self.timeout = False

    def set_reverse_geocode_result(self, address_components: Dict[str, str]):
        """Configure successful reverse geocoding result.

        Args:
            address_components: Dict with city, street, etc.
        """
        self.reverse_geocode_result = address_components
        self.error = None
        self.zero_results = False
        self.timeout = False

    def set_error(self, error_type: str):
        """Configure error response.

        Args:
            error_type: Error type (API_KEY_INVALID, SERVICE_UNAVAILABLE, etc.)
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

    def track_concurrent_requests(self):
        """Enable concurrent request tracking."""
        self.concurrent_requests = 0
        self.max_concurrent_requests = 0

    def set_selective_failures(self, failure_indices: List[int]):
        """Configure selective failures for batch testing.

        Args:
            failure_indices: List of indices that should fail
        """
        self.selective_failures = failure_indices

    def reset(self):
        """Reset all mock state."""
        self.call_count = 0
        self.last_query = None
        self.geocode_result = None
        self.reverse_geocode_result = None
        self.error = None
        self.zero_results = False
        self.timeout = False
        self.concurrent_requests = 0
        self.max_concurrent_requests = 0
        self.selective_failures = []

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
        self.concurrent_requests += 1
        self.max_concurrent_requests = max(
            self.max_concurrent_requests,
            self.concurrent_requests
        )

        # Build query
        query_parts = [address]
        if city:
            query_parts.append(city)
        query_parts.append(country)
        self.last_query = ", ".join(query_parts)

        try:
            # Simulate network delay
            await asyncio.sleep(0.01)

            # Check for selective failure
            if self.call_count - 1 in self.selective_failures:
                raise Exception("ZERO_RESULTS")

            # Check for timeout
            if self.timeout:
                raise asyncio.TimeoutError("Request timeout")

            # Check for error
            if self.error:
                raise Exception(f"Google Maps API Error: {self.error}")

            # Check for zero results
            if self.zero_results:
                raise Exception("ZERO_RESULTS")

            # Return configured result
            if self.geocode_result:
                return self.geocode_result

            # Default result
            return (41.311158, 69.279737, "ROOFTOP")

        finally:
            self.concurrent_requests -= 1

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float
    ) -> Dict[str, str]:
        """Mock reverse geocoding request.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            Address components dict

        Raises:
            Exception: If error configured
        """
        self.call_count += 1

        # Simulate network delay
        await asyncio.sleep(0.01)

        # Check for zero results
        if self.zero_results:
            raise Exception("ZERO_RESULTS")

        # Check for error
        if self.error:
            raise Exception(f"Google Maps API Error: {self.error}")

        # Return configured result
        if self.reverse_geocode_result:
            return self.reverse_geocode_result

        # Default result
        return {
            "full_address": "Tashkent, Yakkasaray, Independence st., 1",
            "city": "Tashkent",
            "district": "Yakkasaray",
            "street": "Independence st.",
            "house_number": "1",
            "country": "Uzbekistan"
        }
