"""
Geocoding Service
UK Management Bot - Integration Service

Provides unified geocoding interface with automatic provider fallback:
- Primary: Google Maps
- Fallback: Yandex Maps
"""

import logging
from typing import Optional, Dict, Any, Tuple, List
from enum import Enum

from app.adapters.google_maps_adapter import GoogleMapsAdapter
from app.adapters.yandex_maps_adapter import YandexMapsAdapter

logger = logging.getLogger(__name__)


class GeocodingProvider(str, Enum):
    """Geocoding provider enum"""
    GOOGLE_MAPS = "google_maps"
    YANDEX_MAPS = "yandex_maps"
    AUTO = "auto"  # Automatic fallback


class GeocodingService:
    """
    Unified Geocoding Service

    Features:
    - Multi-provider support (Google Maps, Yandex Maps)
    - Automatic fallback on provider failure
    - Provider health tracking
    - Consistent response format
    """

    def __init__(
        self,
        management_company_id: str,
        google_api_key: Optional[str] = None,
        yandex_api_key: Optional[str] = None,
        primary_provider: GeocodingProvider = GeocodingProvider.GOOGLE_MAPS
    ):
        """
        Initialize Geocoding Service

        Args:
            management_company_id: Tenant ID
            google_api_key: Google Maps API key
            yandex_api_key: Yandex Maps API key
            primary_provider: Primary provider to use
        """
        self.management_company_id = management_company_id
        self.primary_provider = primary_provider

        # Initialize adapters
        self.google_adapter = GoogleMapsAdapter(
            management_company_id=management_company_id,
            api_key=google_api_key
        )

        self.yandex_adapter = YandexMapsAdapter(
            management_company_id=management_company_id,
            api_key=yandex_api_key
        )

        # Provider health status
        self._provider_health: Dict[str, bool] = {
            GeocodingProvider.GOOGLE_MAPS: True,
            GeocodingProvider.YANDEX_MAPS: True
        }

    async def initialize(self) -> None:
        """Initialize all adapters"""
        try:
            # Initialize Google Maps
            try:
                await self.google_adapter.initialize()
                self._provider_health[GeocodingProvider.GOOGLE_MAPS] = True
                logger.info("✅ Google Maps adapter initialized")
            except Exception as e:
                logger.warning(f"⚠️ Google Maps adapter failed to initialize: {e}")
                self._provider_health[GeocodingProvider.GOOGLE_MAPS] = False

            # Initialize Yandex Maps
            try:
                await self.yandex_adapter.initialize()
                self._provider_health[GeocodingProvider.YANDEX_MAPS] = True
                logger.info("✅ Yandex Maps adapter initialized")
            except Exception as e:
                logger.warning(f"⚠️ Yandex Maps adapter failed to initialize: {e}")
                self._provider_health[GeocodingProvider.YANDEX_MAPS] = False

            # Check if at least one provider is available
            if not any(self._provider_health.values()):
                raise RuntimeError("No geocoding providers available")

            logger.info("✅ Geocoding service initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize geocoding service: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown all adapters"""
        try:
            await self.google_adapter.shutdown()
            await self.yandex_adapter.shutdown()
            logger.info("✅ Geocoding service shutdown complete")

        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all providers

        Returns:
            Dict with provider health status
        """
        health = {}

        # Check Google Maps
        try:
            google_healthy = await self.google_adapter.health_check()
            health[GeocodingProvider.GOOGLE_MAPS] = {
                "status": "healthy" if google_healthy else "unhealthy",
                "available": google_healthy
            }
            self._provider_health[GeocodingProvider.GOOGLE_MAPS] = google_healthy
        except Exception as e:
            health[GeocodingProvider.GOOGLE_MAPS] = {
                "status": "error",
                "error": str(e),
                "available": False
            }
            self._provider_health[GeocodingProvider.GOOGLE_MAPS] = False

        # Check Yandex Maps
        try:
            yandex_healthy = await self.yandex_adapter.health_check()
            health[GeocodingProvider.YANDEX_MAPS] = {
                "status": "healthy" if yandex_healthy else "unhealthy",
                "available": yandex_healthy
            }
            self._provider_health[GeocodingProvider.YANDEX_MAPS] = yandex_healthy
        except Exception as e:
            health[GeocodingProvider.YANDEX_MAPS] = {
                "status": "error",
                "error": str(e),
                "available": False
            }
            self._provider_health[GeocodingProvider.YANDEX_MAPS] = False

        # Overall status
        health["overall"] = {
            "status": "healthy" if any(self._provider_health.values()) else "down",
            "available_providers": sum(1 for v in self._provider_health.values() if v)
        }

        return health

    async def geocode(
        self,
        address: str,
        language: str = "ru",
        region: str = "UZ",
        provider: GeocodingProvider = GeocodingProvider.AUTO,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Geocode address to coordinates

        Args:
            address: Full address to geocode
            language: Language code
            region: Region bias
            provider: Provider to use (AUTO for automatic fallback)
            request_id: Optional request ID for tracing

        Returns:
            Dict with geocoding result and provider used

        Raises:
            RuntimeError: All providers failed
        """
        providers_to_try = self._get_provider_order(provider)

        last_error = None
        for prov in providers_to_try:
            try:
                adapter = self._get_adapter(prov)

                result = await adapter.geocode(
                    address=address,
                    language=language,
                    region=region,
                    request_id=request_id
                )

                # Mark provider as healthy
                self._provider_health[prov] = True

                # Add metadata
                result["used_provider"] = prov
                result["attempted_providers"] = [p for p in providers_to_try[:providers_to_try.index(prov) + 1]]

                logger.info(f"✅ Geocoded with {prov}: {address[:50]}")

                return result

            except Exception as e:
                logger.warning(f"⚠️ Provider {prov} failed for geocoding: {e}")
                self._provider_health[prov] = False
                last_error = e
                continue

        # All providers failed
        raise RuntimeError(
            f"All geocoding providers failed for address: {address}. "
            f"Last error: {last_error}"
        )

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language: str = "ru",
        provider: GeocodingProvider = GeocodingProvider.AUTO,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reverse geocode coordinates to address

        Args:
            latitude: Latitude
            longitude: Longitude
            language: Language code
            provider: Provider to use (AUTO for automatic fallback)
            request_id: Optional request ID for tracing

        Returns:
            Dict with reverse geocoding result and provider used

        Raises:
            RuntimeError: All providers failed
        """
        providers_to_try = self._get_provider_order(provider)

        last_error = None
        for prov in providers_to_try:
            try:
                adapter = self._get_adapter(prov)

                result = await adapter.reverse_geocode(
                    latitude=latitude,
                    longitude=longitude,
                    language=language,
                    request_id=request_id
                )

                # Mark provider as healthy
                self._provider_health[prov] = True

                # Add metadata
                result["used_provider"] = prov
                result["attempted_providers"] = [p for p in providers_to_try[:providers_to_try.index(prov) + 1]]

                logger.info(f"✅ Reverse geocoded with {prov}: ({latitude}, {longitude})")

                return result

            except Exception as e:
                logger.warning(f"⚠️ Provider {prov} failed for reverse geocoding: {e}")
                self._provider_health[prov] = False
                last_error = e
                continue

        # All providers failed
        raise RuntimeError(
            f"All geocoding providers failed for coordinates: ({latitude}, {longitude}). "
            f"Last error: {last_error}"
        )

    async def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        provider: GeocodingProvider = GeocodingProvider.GOOGLE_MAPS,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate distance between two points

        Args:
            origin: (latitude, longitude) tuple
            destination: (latitude, longitude) tuple
            provider: Provider to use (distance calculation doesn't need fallback)
            request_id: Optional request ID for tracing

        Returns:
            Dict with distance calculation

        Note:
            This is a straight-line distance calculation.
        """
        try:
            adapter = self._get_adapter(provider)

            result = await adapter.calculate_distance(
                origin=origin,
                destination=destination,
                request_id=request_id
            )

            result["used_provider"] = provider

            return result

        except Exception as e:
            logger.error(f"❌ Distance calculation failed: {e}")
            raise

    def _get_provider_order(self, provider: GeocodingProvider) -> List[GeocodingProvider]:
        """
        Get provider order for fallback

        Args:
            provider: Requested provider

        Returns:
            List of providers in order to try
        """
        if provider == GeocodingProvider.AUTO:
            # Try primary first, then fallback
            if self.primary_provider == GeocodingProvider.GOOGLE_MAPS:
                return [GeocodingProvider.GOOGLE_MAPS, GeocodingProvider.YANDEX_MAPS]
            else:
                return [GeocodingProvider.YANDEX_MAPS, GeocodingProvider.GOOGLE_MAPS]

        elif provider == GeocodingProvider.GOOGLE_MAPS:
            # Try Google only, then fallback to Yandex if unhealthy
            if self._provider_health[GeocodingProvider.GOOGLE_MAPS]:
                return [GeocodingProvider.GOOGLE_MAPS]
            else:
                return [GeocodingProvider.YANDEX_MAPS]

        elif provider == GeocodingProvider.YANDEX_MAPS:
            # Try Yandex only, then fallback to Google if unhealthy
            if self._provider_health[GeocodingProvider.YANDEX_MAPS]:
                return [GeocodingProvider.YANDEX_MAPS]
            else:
                return [GeocodingProvider.GOOGLE_MAPS]

        return [provider]

    def _get_adapter(self, provider: GeocodingProvider):
        """
        Get adapter for provider

        Args:
            provider: Provider enum

        Returns:
            Adapter instance

        Raises:
            ValueError: Unknown provider
        """
        if provider == GeocodingProvider.GOOGLE_MAPS:
            return self.google_adapter
        elif provider == GeocodingProvider.YANDEX_MAPS:
            return self.yandex_adapter
        else:
            raise ValueError(f"Unknown provider: {provider}")
