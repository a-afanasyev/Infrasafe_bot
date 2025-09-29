"""
Request Service - Geocoding Service
UK Management Bot - Request Management System

Address geocoding and coordinate normalization service.
"""

import logging
import asyncio
import re
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models import Request
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class GeocodingResult:
    """Geocoding operation result"""
    latitude: Optional[float]
    longitude: Optional[float]
    formatted_address: Optional[str]
    confidence: float
    source: str
    components: Dict[str, Any]


@dataclass
class AddressComponents:
    """Structured address components"""
    street: Optional[str] = None
    house_number: Optional[str] = None
    apartment: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    postal_code: Optional[str] = None


class GeocodingError(Exception):
    """Base geocoding exception"""
    pass


class GeocodingServiceUnavailable(GeocodingError):
    """Geocoding service unavailable"""
    pass


class GeocodingQuotaExceeded(GeocodingError):
    """API quota exceeded"""
    pass


class GeocodingService:
    """
    Address geocoding service with multiple providers and fallbacks

    Supports:
    - OpenStreetMap Nominatim (free, no API key required)
    - Google Maps Geocoding API (high accuracy, requires API key)
    - Yandex Maps API (good for CIS region)
    - Local address normalization for Tashkent
    """

    def __init__(self):
        self.timeout = 10  # seconds
        self.user_agent = "UK-Management-Bot/1.0 Request-Service"

        # API configurations
        self.google_api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        self.yandex_api_key = getattr(settings, 'YANDEX_MAPS_API_KEY', None)

        # Tashkent district mapping for local geocoding
        self.tashkent_districts = {
            'алмазар': (41.2995, 69.2401),
            'бектемир': (41.2050, 69.3340),
            'мирзо-улугбек': (41.3157, 69.3340),
            'мирзо улугбек': (41.3157, 69.3340),
            'сергели': (41.2200, 69.2230),
            'олмазор': (41.3457, 69.2980),
            'учтепа': (41.2820, 69.1740),
            'чиланзар': (41.2756, 69.2034),
            'шайхантахур': (41.3269, 69.2910),
            'юнусабад': (41.3670, 69.2890),
            'яккасарай': (41.2890, 69.2270),
            'янгихает': (41.2418, 69.3200)
        }

    async def geocode_address(
        self,
        address: str,
        prefer_local: bool = True
    ) -> Optional[GeocodingResult]:
        """
        Geocode address using multiple providers with fallbacks

        Args:
            address: Address string to geocode
            prefer_local: Try local geocoding first for Tashkent addresses

        Returns:
            GeocodingResult with coordinates and metadata
        """
        try:
            address = address.strip()
            if not address:
                return None

            # Try local geocoding first for Tashkent addresses
            if prefer_local and self._is_tashkent_address(address):
                local_result = await self._geocode_local_tashkent(address)
                if local_result and local_result.confidence > 0.6:
                    return local_result

            # Try external geocoding services
            providers = []

            # Add OpenStreetMap (always available)
            providers.append(self._geocode_openstreetmap)

            # Add Google Maps if API key available
            if self.google_api_key:
                providers.append(self._geocode_google_maps)

            # Add Yandex if API key available (good for CIS)
            if self.yandex_api_key:
                providers.append(self._geocode_yandex_maps)

            # Try providers in order
            for provider in providers:
                try:
                    result = await provider(address)
                    if result and result.confidence > 0.5:
                        return result
                except Exception as e:
                    logger.warning(f"Geocoding provider failed: {e}")
                    continue

            # Final fallback to local if nothing worked
            if not prefer_local and self._is_tashkent_address(address):
                return await self._geocode_local_tashkent(address)

            return None

        except Exception as e:
            logger.error(f"Geocoding failed for address '{address}': {e}")
            return None

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float
    ) -> Optional[GeocodingResult]:
        """
        Reverse geocode coordinates to address

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            GeocodingResult with address information
        """
        try:
            # Validate coordinates
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                raise ValueError(f"Invalid coordinates: {latitude}, {longitude}")

            # Try OpenStreetMap reverse geocoding
            result = await self._reverse_geocode_openstreetmap(latitude, longitude)
            if result:
                return result

            # Try Google Maps if available
            if self.google_api_key:
                result = await self._reverse_geocode_google_maps(latitude, longitude)
                if result:
                    return result

            return None

        except Exception as e:
            logger.error(f"Reverse geocoding failed for {latitude}, {longitude}: {e}")
            return None

    async def normalize_coordinates(
        self,
        latitude: Optional[float],
        longitude: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Normalize and validate coordinates

        Args:
            latitude: Raw latitude value
            longitude: Raw longitude value

        Returns:
            Tuple of normalized (latitude, longitude) or (None, None)
        """
        try:
            if latitude is None or longitude is None:
                return None, None

            # Validate ranges
            if not (-90 <= latitude <= 90):
                logger.warning(f"Invalid latitude: {latitude}")
                return None, None

            if not (-180 <= longitude <= 180):
                logger.warning(f"Invalid longitude: {longitude}")
                return None, None

            # Round to reasonable precision (6 decimal places ≈ 0.1m accuracy)
            normalized_lat = round(float(latitude), 6)
            normalized_lng = round(float(longitude), 6)

            return normalized_lat, normalized_lng

        except (ValueError, TypeError) as e:
            logger.warning(f"Coordinate normalization failed: {e}")
            return None, None

    async def geocode_request(
        self,
        db: AsyncSession,
        request_number: str,
        force_update: bool = False
    ) -> bool:
        """
        Geocode request address and update coordinates in database

        Args:
            db: Database session
            request_number: Request number to geocode
            force_update: Update even if coordinates already exist

        Returns:
            True if geocoding was successful
        """
        try:
            # Get request
            query = select(Request).where(Request.request_number == request_number)
            result = await db.execute(query)
            request = result.scalar_one_or_none()

            if not request:
                logger.warning(f"Request {request_number} not found for geocoding")
                return False

            # Skip if coordinates already exist and not forcing update
            if not force_update and request.latitude and request.longitude:
                logger.debug(f"Request {request_number} already has coordinates")
                return True

            # Skip if no address
            if not request.address:
                logger.debug(f"Request {request_number} has no address to geocode")
                return False

            # Perform geocoding
            geocoding_result = await self.geocode_address(request.address)

            if not geocoding_result:
                logger.warning(f"Failed to geocode address: {request.address}")
                return False

            # Update request with coordinates
            update_query = update(Request).where(
                Request.request_number == request_number
            ).values(
                latitude=geocoding_result.latitude,
                longitude=geocoding_result.longitude
            )

            await db.execute(update_query)
            await db.commit()

            logger.info(
                f"Geocoded request {request_number}: {request.address} -> "
                f"({geocoding_result.latitude}, {geocoding_result.longitude}) "
                f"via {geocoding_result.source}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to geocode request {request_number}: {e}")
            await db.rollback()
            return False

    def _is_tashkent_address(self, address: str) -> bool:
        """Check if address appears to be in Tashkent"""
        address_lower = address.lower()

        # Check for Tashkent indicators
        tashkent_indicators = [
            'ташкент', 'tashkent', 'toshkent',
            'узбекистан', 'uzbekistan', 'ўзбекистон'
        ]

        # Check for district names
        tashkent_districts = list(self.tashkent_districts.keys())

        all_indicators = tashkent_indicators + tashkent_districts

        return any(indicator in address_lower for indicator in all_indicators)

    async def _geocode_local_tashkent(self, address: str) -> Optional[GeocodingResult]:
        """Local geocoding for Tashkent addresses using district mapping"""
        try:
            address_lower = address.lower()

            # Find district in address
            district_found = None
            district_coords = None

            for district, coords in self.tashkent_districts.items():
                if district in address_lower:
                    district_found = district
                    district_coords = coords
                    break

            if not district_coords:
                return None

            # Extract house/building number for offset
            house_match = re.search(r'дом\s*(\d+)|д\.?\s*(\d+)|(\d+)', address_lower)
            house_offset = 0.001  # Default small offset

            if house_match:
                house_num = int(house_match.group(1) or house_match.group(2) or house_match.group(3))
                # Create small offset based on house number
                house_offset = (house_num % 100) * 0.0001

            # Calculate coordinates with small offset
            lat = district_coords[0] + house_offset
            lng = district_coords[1] + (house_offset * 0.5)

            # Normalize coordinates
            lat, lng = await self.normalize_coordinates(lat, lng)
            if not lat or not lng:
                return None

            return GeocodingResult(
                latitude=lat,
                longitude=lng,
                formatted_address=f"{address}, {district_found.title()}, Ташкент, Узбекистан",
                confidence=0.7,  # Medium confidence for local geocoding
                source="local_tashkent",
                components={
                    "district": district_found,
                    "city": "Ташкент",
                    "country": "Узбекистан"
                }
            )

        except Exception as e:
            logger.error(f"Local Tashkent geocoding failed: {e}")
            return None

    async def _geocode_openstreetmap(self, address: str) -> Optional[GeocodingResult]:
        """Geocode using OpenStreetMap Nominatim"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    'q': address,
                    'format': 'json',
                    'limit': 1,
                    'addressdetails': 1
                }
                headers = {
                    'User-Agent': self.user_agent
                }

                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()

                data = response.json()
                if not data:
                    return None

                result = data[0]
                lat = float(result['lat'])
                lng = float(result['lon'])

                # Normalize coordinates
                lat, lng = await self.normalize_coordinates(lat, lng)
                if not lat or not lng:
                    return None

                # Calculate confidence based on importance
                importance = float(result.get('importance', 0.5))
                confidence = min(importance * 2, 1.0)  # Scale to 0-1

                return GeocodingResult(
                    latitude=lat,
                    longitude=lng,
                    formatted_address=result.get('display_name'),
                    confidence=confidence,
                    source="openstreetmap",
                    components=result.get('address', {})
                )

        except Exception as e:
            logger.error(f"OpenStreetMap geocoding failed: {e}")
            return None

    async def _geocode_google_maps(self, address: str) -> Optional[GeocodingResult]:
        """Geocode using Google Maps Geocoding API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = "https://maps.googleapis.com/maps/api/geocode/json"
                params = {
                    'address': address,
                    'key': self.google_api_key
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if data['status'] != 'OK' or not data['results']:
                    return None

                result = data['results'][0]
                location = result['geometry']['location']
                lat = location['lat']
                lng = location['lng']

                # Normalize coordinates
                lat, lng = await self.normalize_coordinates(lat, lng)
                if not lat or not lng:
                    return None

                # Calculate confidence based on location type
                location_type = result['geometry'].get('location_type', 'APPROXIMATE')
                confidence_map = {
                    'ROOFTOP': 1.0,
                    'RANGE_INTERPOLATED': 0.9,
                    'GEOMETRIC_CENTER': 0.8,
                    'APPROXIMATE': 0.6
                }
                confidence = confidence_map.get(location_type, 0.6)

                return GeocodingResult(
                    latitude=lat,
                    longitude=lng,
                    formatted_address=result.get('formatted_address'),
                    confidence=confidence,
                    source="google_maps",
                    components={
                        'address_components': result.get('address_components', []),
                        'location_type': location_type
                    }
                )

        except Exception as e:
            logger.error(f"Google Maps geocoding failed: {e}")
            return None

    async def _geocode_yandex_maps(self, address: str) -> Optional[GeocodingResult]:
        """Geocode using Yandex Maps Geocoding API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = "https://geocode-maps.yandex.ru/1.x/"
                params = {
                    'apikey': self.yandex_api_key,
                    'geocode': address,
                    'format': 'json',
                    'results': 1
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                found_count = int(data['response']['GeoObjectCollection']['metaDataProperty']['GeocoderResponseMetaData']['found'])

                if found_count == 0:
                    return None

                geo_object = data['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']
                coords = geo_object['Point']['pos'].split()
                lng = float(coords[0])  # Yandex returns lng, lat
                lat = float(coords[1])

                # Normalize coordinates
                lat, lng = await self.normalize_coordinates(lat, lng)
                if not lat or not lng:
                    return None

                # Calculate confidence based on precision
                precision = geo_object['metaDataProperty']['GeocoderMetaData'].get('precision', 'other')
                confidence_map = {
                    'exact': 1.0,
                    'number': 0.9,
                    'near': 0.8,
                    'range': 0.7,
                    'street': 0.6,
                    'other': 0.5
                }
                confidence = confidence_map.get(precision, 0.5)

                return GeocodingResult(
                    latitude=lat,
                    longitude=lng,
                    formatted_address=geo_object['metaDataProperty']['GeocoderMetaData']['text'],
                    confidence=confidence,
                    source="yandex_maps",
                    components={
                        'precision': precision,
                        'kind': geo_object['metaDataProperty']['GeocoderMetaData'].get('kind')
                    }
                )

        except Exception as e:
            logger.error(f"Yandex Maps geocoding failed: {e}")
            return None

    async def _reverse_geocode_openstreetmap(
        self,
        latitude: float,
        longitude: float
    ) -> Optional[GeocodingResult]:
        """Reverse geocode using OpenStreetMap Nominatim"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = "https://nominatim.openstreetmap.org/reverse"
                params = {
                    'lat': latitude,
                    'lon': longitude,
                    'format': 'json',
                    'addressdetails': 1
                }
                headers = {
                    'User-Agent': self.user_agent
                }

                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()

                data = response.json()
                if 'error' in data:
                    return None

                return GeocodingResult(
                    latitude=latitude,
                    longitude=longitude,
                    formatted_address=data.get('display_name'),
                    confidence=0.8,  # Good confidence for reverse geocoding
                    source="openstreetmap_reverse",
                    components=data.get('address', {})
                )

        except Exception as e:
            logger.error(f"OpenStreetMap reverse geocoding failed: {e}")
            return None

    async def _reverse_geocode_google_maps(
        self,
        latitude: float,
        longitude: float
    ) -> Optional[GeocodingResult]:
        """Reverse geocode using Google Maps Geocoding API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = "https://maps.googleapis.com/maps/api/geocode/json"
                params = {
                    'latlng': f"{latitude},{longitude}",
                    'key': self.google_api_key
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if data['status'] != 'OK' or not data['results']:
                    return None

                result = data['results'][0]

                return GeocodingResult(
                    latitude=latitude,
                    longitude=longitude,
                    formatted_address=result.get('formatted_address'),
                    confidence=0.9,  # High confidence for Google reverse geocoding
                    source="google_maps_reverse",
                    components={
                        'address_components': result.get('address_components', [])
                    }
                )

        except Exception as e:
            logger.error(f"Google Maps reverse geocoding failed: {e}")
            return None


# Create global geocoding service instance
geocoding_service = GeocodingService()