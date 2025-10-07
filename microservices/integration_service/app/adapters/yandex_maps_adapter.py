"""
Yandex Maps Adapter
UK Management Bot - Integration Service

Provides geocoding services using Yandex Maps API:
- Address to coordinates (geocoding)
- Coordinates to address (reverse geocoding)
- Distance calculations
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Tuple

from yandex_geocoder import Client as YandexClient
from yandex_geocoder.exceptions import YandexGeocoderException

from app.adapters.base import BaseAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class YandexMapsAdapter(BaseAdapter):
    """
    Yandex Maps Geocoding Adapter

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
        Initialize Yandex Maps adapter

        Args:
            management_company_id: Tenant ID
            api_key: Yandex Maps API key
            config: Optional configuration
        """
        super().__init__(
            service_name="yandex_maps",
            service_type="geocoding",
            management_company_id=management_company_id,
            config=config or {}
        )

        self.api_key = api_key or settings.YANDEX_MAPS_API_KEY
        self.rate_limit_per_minute = settings.YANDEX_MAPS_RATE_LIMIT_PER_MINUTE

        self._client: Optional[YandexClient] = None
        self._request_count: int = 0
        self._request_window_start: float = 0.0

    async def initialize(self) -> None:
        """Initialize Yandex Maps client"""
        try:
            if not self.api_key:
                self.logger.warning("⚠️ Yandex Maps API key not configured, using free tier")
                # Yandex allows limited free usage without API key
                self._client = YandexClient()
            else:
                self._client = YandexClient(api_key=self.api_key)

            # Test API connectivity
            await self.health_check()

            self.logger.info(f"✅ Yandex Maps adapter initialized for tenant {self.management_company_id}")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Yandex Maps adapter: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown Yandex Maps client"""
        try:
            # yandex-geocoder client doesn't require explicit cleanup
            self._client = None
            self.logger.info("✅ Yandex Maps adapter shutdown complete")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

    async def health_check(self) -> bool:
        """
        Check Yandex Maps API health

        Returns:
            True if API is accessible
        """
        try:
            if not self._client:
                return False

            # Simple geocoding test
            result = await self._run_in_executor(
                self._client.coordinates,
                "Москва, Красная площадь"
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

        yandex-geocoder library is synchronous
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
            region: Region bias (not used by Yandex, kept for interface compatibility)
            request_id: Optional request ID for tracing

        Returns:
            Dict with latitude, longitude, formatted_address, address_components

        Raises:
            YandexGeocoderException: Yandex API error
            ValueError: Invalid address
        """
        return await self._execute_with_logging(
            operation="geocode",
            func=lambda: self._geocode_impl(address, language),
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
        language: str
    ) -> Dict[str, Any]:
        """Implementation of geocode"""
        await self._rate_limit()

        if not self._client:
            raise RuntimeError("Adapter not initialized")

        try:
            # Call Yandex Maps API
            coordinates = await self._run_in_executor(
                self._client.coordinates,
                address,
                lang=language
            )

            if not coordinates:
                raise ValueError(f"Address not found: {address}")

            # Get full address info
            result = await self._run_in_executor(
                self._client.address,
                address,
                lang=language
            )

            return {
                "latitude": coordinates[0],
                "longitude": coordinates[1],
                "formatted_address": result if result else address,
                "address_components": self._parse_address_components(result),
                "place_id": None,  # Yandex doesn't provide place_id
                "location_type": "APPROXIMATE",  # Yandex doesn't provide precision
                "confidence": 0.8,  # Default confidence for Yandex
                "provider": "yandex_maps"
            }

        except YandexGeocoderException as e:
            self.logger.error(f"Yandex Maps API error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
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
            YandexGeocoderException: Yandex API error
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
            # Call Yandex Maps API
            result = await self._run_in_executor(
                self._client.address,
                f"{latitude},{longitude}",
                lang=language
            )

            if not result:
                raise ValueError(f"Location not found: ({latitude}, {longitude})")

            return {
                "formatted_address": result,
                "address_components": self._parse_address_components(result),
                "place_id": None,
                "location_type": "APPROXIMATE",
                "provider": "yandex_maps"
            }

        except YandexGeocoderException as e:
            self.logger.error(f"Yandex Maps API error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
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

    def _parse_address_components(self, formatted_address: str) -> list:
        """
        Parse Yandex formatted address into components

        Yandex doesn't provide structured address components like Google,
        so we do basic parsing.

        Args:
            formatted_address: Full address string

        Returns:
            List of address component dicts
        """
        if not formatted_address:
            return []

        components = []
        parts = formatted_address.split(', ')

        for part in parts:
            components.append({
                "long_name": part,
                "short_name": part,
                "types": ["premise"]  # Generic type
            })

        return components
