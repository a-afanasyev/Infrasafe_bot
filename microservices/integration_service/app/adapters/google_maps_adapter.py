"""
Google Maps Adapter
UK Management Bot - Integration Service

Provides geocoding services using Google Maps API:
- Address to coordinates (geocoding)
- Coordinates to address (reverse geocoding)
- Distance calculations
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

import googlemaps
from googlemaps.exceptions import ApiError, TransportError, Timeout

from app.adapters.base import BaseAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleMapsAdapter(BaseAdapter):
    """
    Google Maps Geocoding Adapter

    Features:
    - Geocoding (address → coordinates)
    - Reverse geocoding (coordinates → address)
    - Distance calculation
    - Rate limiting (50 req/min)
    - Automatic retries
    """

    def __init__(
        self,
        management_company_id: str,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Google Maps adapter

        Args:
            management_company_id: Tenant ID
            api_key: Google Maps API key
            config: Optional configuration
        """
        super().__init__(
            service_name="google_maps",
            service_type="geocoding",
            management_company_id=management_company_id,
            config=config or {}
        )

        self.api_key = api_key or settings.GOOGLE_MAPS_API_KEY
        self.rate_limit_per_minute = settings.GOOGLE_MAPS_RATE_LIMIT_PER_MINUTE

        self._client: Optional[googlemaps.Client] = None
        self._request_count: int = 0
        self._request_window_start: float = 0.0

    async def initialize(self) -> None:
        """Initialize Google Maps client"""
        try:
            if not self.api_key:
                raise ValueError("Google Maps API key not configured")

            # Create synchronous client (googlemaps library is sync-only)
            self._client = googlemaps.Client(key=self.api_key)

            # Test API connectivity
            await self.health_check()

            self.logger.info(f"✅ Google Maps adapter initialized for tenant {self.management_company_id}")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Google Maps adapter: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown Google Maps client"""
        try:
            # googlemaps client doesn't require explicit cleanup
            self._client = None
            self.logger.info("✅ Google Maps adapter shutdown complete")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

    async def health_check(self) -> bool:
        """
        Check Google Maps API health

        Returns:
            True if API is accessible
        """
        try:
            if not self._client:
                return False

            # Simple geocoding test (doesn't count against quota much)
            # Use a well-known address that should always work
            result = await self._run_in_executor(
                self._client.geocode,
                "1600 Amphitheatre Parkway, Mountain View, CA"
            )

            return bool(result)

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    async def _rate_limit(self) -> None:
        """
        Enforce rate limiting (50 req/min)

        Uses token bucket algorithm with async sleep.
        """
        current_time = asyncio.get_event_loop().time()

        # Reset window if needed (every 60 seconds)
        if current_time - self._request_window_start >= 60.0:
            self._request_window_start = current_time
            self._request_count = 0

        # Check if we've exceeded rate limit
        if self._request_count >= self.rate_limit_per_minute:
            # Calculate sleep time until window resets
            sleep_time = 60.0 - (current_time - self._request_window_start)
            if sleep_time > 0:
                self.logger.warning(
                    f"⚠️ Rate limit reached ({self.rate_limit_per_minute} req/min), "
                    f"sleeping for {sleep_time:.2f}s"
                )
                await asyncio.sleep(sleep_time)

                # Reset window
                self._request_window_start = asyncio.get_event_loop().time()
                self._request_count = 0

        # Increment request count
        self._request_count += 1

    async def _run_in_executor(self, func, *args, **kwargs):
        """
        Run synchronous function in thread pool

        googlemaps library is synchronous, so we need to run it in executor
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def geocode(
        self,
        address: str,
        language: str = "ru",
        region: str = "UZ",
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Geocode address to coordinates

        Args:
            address: Full address to geocode
            language: Language code (e.g., "ru", "uz")
            region: Region bias (e.g., "UZ" for Uzbekistan)
            request_id: Optional request ID for tracing

        Returns:
            Dict with latitude, longitude, formatted_address, address_components

        Raises:
            ApiError: Google Maps API error
            ValueError: Invalid address
        """
        return await self._execute_with_logging(
            operation="geocode",
            func=lambda: self._geocode_impl(address, language, region),
            params={
                "address": address,
                "language": language,
                "region": region
            },
            request_id=request_id
        )

    async def _geocode_impl(
        self,
        address: str,
        language: str,
        region: str
    ) -> Dict[str, Any]:
        """Implementation of geocode"""
        await self._rate_limit()

        if not self._client:
            raise RuntimeError("Adapter not initialized")

        try:
            # Call Google Maps API
            results = await self._run_in_executor(
                self._client.geocode,
                address,
                language=language,
                region=region
            )

            if not results:
                raise ValueError(f"Address not found: {address}")

            # Parse first result
            result = results[0]
            location = result['geometry']['location']

            return {
                "latitude": location['lat'],
                "longitude": location['lng'],
                "formatted_address": result['formatted_address'],
                "address_components": result.get('address_components', []),
                "place_id": result.get('place_id'),
                "location_type": result['geometry'].get('location_type'),
                "confidence": self._calculate_confidence(result),
                "provider": "google_maps"
            }

        except (ApiError, TransportError, Timeout) as e:
            self.logger.error(f"Google Maps API error: {e}")
            raise

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language: str = "ru",
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reverse geocode coordinates to address

        Args:
            latitude: Latitude
            longitude: Longitude
            language: Language code
            request_id: Optional request ID for tracing

        Returns:
            Dict with formatted_address, address_components

        Raises:
            ApiError: Google Maps API error
            ValueError: Invalid coordinates
        """
        return await self._execute_with_logging(
            operation="reverse_geocode",
            func=lambda: self._reverse_geocode_impl(latitude, longitude, language),
            params={
                "latitude": latitude,
                "longitude": longitude,
                "language": language
            },
            request_id=request_id
        )

    async def _reverse_geocode_impl(
        self,
        latitude: float,
        longitude: float,
        language: str
    ) -> Dict[str, Any]:
        """Implementation of reverse_geocode"""
        await self._rate_limit()

        if not self._client:
            raise RuntimeError("Adapter not initialized")

        try:
            # Call Google Maps API
            results = await self._run_in_executor(
                self._client.reverse_geocode,
                (latitude, longitude),
                language=language
            )

            if not results:
                raise ValueError(f"Location not found: ({latitude}, {longitude})")

            # Parse first result (most specific)
            result = results[0]

            return {
                "formatted_address": result['formatted_address'],
                "address_components": result.get('address_components', []),
                "place_id": result.get('place_id'),
                "location_type": result['geometry'].get('location_type'),
                "provider": "google_maps"
            }

        except (ApiError, TransportError, Timeout) as e:
            self.logger.error(f"Google Maps API error: {e}")
            raise

    async def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate distance between two points (Haversine formula)

        Args:
            origin: (latitude, longitude) tuple
            destination: (latitude, longitude) tuple
            request_id: Optional request ID for tracing

        Returns:
            Dict with distance_km, distance_miles, straight_line=True

        Note:
            This is a straight-line distance calculation, not routing distance.
            For routing distance, use Google Maps Distance Matrix API.
        """
        return await self._execute_with_logging(
            operation="calculate_distance",
            func=lambda: self._calculate_distance_impl(origin, destination),
            params={
                "origin": origin,
                "destination": destination
            },
            request_id=request_id
        )

    async def _calculate_distance_impl(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float]
    ) -> Dict[str, Any]:
        """Implementation of calculate_distance"""
        from math import radians, sin, cos, sqrt, atan2

        # Haversine formula
        lat1, lon1 = origin
        lat2, lon2 = destination

        R = 6371  # Earth radius in kilometers

        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)

        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance_km = R * c
        distance_miles = distance_km * 0.621371

        return {
            "distance_km": round(distance_km, 2),
            "distance_miles": round(distance_miles, 2),
            "straight_line": True,
            "origin": {"latitude": lat1, "longitude": lon1},
            "destination": {"latitude": lat2, "longitude": lon2}
        }

    def _calculate_confidence(self, result: Dict[str, Any]) -> float:
        """
        Calculate confidence score for geocoding result

        Based on location_type:
        - ROOFTOP: 1.0 (exact address)
        - RANGE_INTERPOLATED: 0.9 (interpolated)
        - GEOMETRIC_CENTER: 0.7 (center of area)
        - APPROXIMATE: 0.5 (approximate)

        Args:
            result: Google Maps geocoding result

        Returns:
            Confidence score (0.0 - 1.0)
        """
        location_type = result.get('geometry', {}).get('location_type', 'APPROXIMATE')

        confidence_map = {
            'ROOFTOP': 1.0,
            'RANGE_INTERPOLATED': 0.9,
            'GEOMETRIC_CENTER': 0.7,
            'APPROXIMATE': 0.5
        }

        return confidence_map.get(location_type, 0.5)
