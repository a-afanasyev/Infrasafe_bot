"""Building Service - Core Building Management.

Task 2.1: Implement BuildingService Business Logic (P0)
Week 1, Day 2 - Building Directory Implementation
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, and_, or_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from difflib import SequenceMatcher

from models.building import Building
from schemas.building import (
    BuildingCreate, BuildingUpdate, BuildingResponse, BuildingListResponse,
    BuildingFilter, BuildingStatsResponse, CoordinatesResponse
)

logger = logging.getLogger(__name__)


class BuildingService:
    """Service for managing buildings in the directory.

    Provides CRUD operations, search, geocoding support, and statistics
    for the centralized building directory.
    """

    def __init__(self, db: AsyncSession):
        """Initialize BuildingService.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    # ========================================================================
    # Create Operations
    # ========================================================================

    async def create_building(
        self,
        building_data: BuildingCreate,
        management_company_id: UUID,
        created_by: Optional[UUID] = None
    ) -> BuildingResponse:
        """Create a new building in the directory.

        Args:
            building_data: Building creation data
            management_company_id: Management company ID (tenant isolation)
            created_by: User ID who creates the building

        Returns:
            BuildingResponse: Created building

        Raises:
            ValueError: If building data is invalid
        """
        # Note: Duplicate addresses are allowed - different companies or
        # different building records can have same address (e.g., different corpus)

        # Create building instance
        building = Building(
            management_company_id=management_company_id,
            city=building_data.city,
            street=building_data.street,
            house_number=building_data.house_number,
            district=building_data.district,
            building_corpus=building_data.building_corpus,
            postal_code=building_data.postal_code,
            building_type=building_data.building_type,
            floors_count=building_data.floors_count,
            entrance_count=building_data.entrance_count,
            apartments_count=building_data.apartments_count,
            year_built=building_data.year_built,
            notes=building_data.notes,
            extra_data=building_data.extra_data or {},
            created_by=created_by,
            is_active=True
        )

        # Set coordinates if provided
        if building_data.latitude is not None and building_data.longitude is not None:
            building.set_coordinates(
                latitude=float(building_data.latitude),
                longitude=float(building_data.longitude),
                source=building_data.coordinates_source or 'manual'
            )

        self.db.add(building)
        await self.db.flush()
        await self.db.refresh(building)
        await self.db.commit()

        logger.info(
            f"Created building {building.id} at '{building.full_address}' "
            f"for MC {management_company_id}"
        )

        return self._build_response(building)

    # ========================================================================
    # Read Operations
    # ========================================================================

    async def get_building_by_id(
        self,
        building_id: UUID,
        management_company_id: UUID
    ) -> Optional[BuildingResponse]:
        """Get building by ID with tenant isolation.

        Args:
            building_id: Building ID
            management_company_id: Management company ID (tenant isolation)

        Returns:
            Optional[BuildingResponse]: Building or None if not found
        """
        query = select(Building).where(
            and_(
                Building.id == building_id,
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        )

        result = await self.db.execute(query)
        building = result.scalar_one_or_none()

        if not building:
            return None

        return self._build_response(building)

    async def list_buildings(
        self,
        management_company_id: UUID,
        filters: BuildingFilter
    ) -> BuildingListResponse:
        """List buildings with filtering, pagination, and sorting.

        Args:
            management_company_id: Management company ID (tenant isolation)
            filters: Filter, pagination, and sorting parameters

        Returns:
            BuildingListResponse: Paginated list of buildings
        """
        # Build base query with tenant isolation
        query = select(Building).where(
            Building.management_company_id == management_company_id
        )

        # Apply filters
        if filters.city:
            query = query.where(Building.city.ilike(f"%{filters.city}%"))

        if filters.street:
            query = query.where(Building.street.ilike(f"%{filters.street}%"))

        if filters.district:
            query = query.where(Building.district.ilike(f"%{filters.district}%"))

        if filters.building_type:
            query = query.where(Building.building_type == filters.building_type)

        if filters.has_coordinates is not None:
            if filters.has_coordinates:
                query = query.where(
                    and_(
                        Building.latitude.is_not(None),
                        Building.longitude.is_not(None)
                    )
                )
            else:
                query = query.where(
                    or_(
                        Building.latitude.is_(None),
                        Building.longitude.is_(None)
                    )
                )

        if filters.is_active is not None:
            query = query.where(Building.is_active == filters.is_active)

        # Get total count
        count_query = select(func.count()).select_from(query.alias())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Building, filters.sort_by, Building.created_at)
        if filters.sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (filters.page - 1) * filters.page_size
        query = query.offset(offset).limit(filters.page_size)

        # Execute query
        result = await self.db.execute(query)
        buildings = result.scalars().all()

        # Calculate total pages
        total_pages = (total + filters.page_size - 1) // filters.page_size

        return BuildingListResponse(
            items=[self._build_response(b) for b in buildings],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages
        )

    async def search_buildings(
        self,
        management_company_id: UUID,
        query_text: str,
        city: Optional[str] = None,
        limit: int = 10
    ) -> List[BuildingResponse]:
        """Search buildings by address components.

        Uses fuzzy matching for address search.

        Args:
            management_company_id: Management company ID (tenant isolation)
            query_text: Search query (street, house number, etc.)
            city: Optional city filter
            limit: Maximum results (default: 10)

        Returns:
            List[BuildingResponse]: Matching buildings
        """
        # Build base query
        query = select(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        )

        # Filter by city if provided
        if city:
            query = query.where(Building.city == city)

        # Search in address components
        search_filter = or_(
            Building.street.ilike(f"%{query_text}%"),
            Building.house_number.ilike(f"%{query_text}%"),
            Building.district.ilike(f"%{query_text}%")
        )
        query = query.where(search_filter)

        # Limit results
        query = query.limit(limit)

        result = await self.db.execute(query)
        buildings = result.scalars().all()

        return [self._build_response(b) for b in buildings]

    # ========================================================================
    # Update Operations
    # ========================================================================

    async def update_building(
        self,
        building_id: UUID,
        management_company_id: UUID,
        building_data: BuildingUpdate,
        updated_by: Optional[UUID] = None
    ) -> Optional[BuildingResponse]:
        """Update building information.

        Args:
            building_id: Building ID
            management_company_id: Management company ID (tenant isolation)
            building_data: Update data
            updated_by: User ID who updates the building

        Returns:
            Optional[BuildingResponse]: Updated building or None if not found

        Raises:
            ValueError: If update would create duplicate address
        """
        # Get existing building
        building = await self._get_building_or_none(building_id, management_company_id)
        if not building:
            return None

        # Check for address duplication if address fields are being updated
        address_changed = any([
            building_data.city and building_data.city != building.city,
            building_data.street and building_data.street != building.street,
            building_data.house_number and building_data.house_number != building.house_number,
            building_data.building_corpus != building.building_corpus  # Can be None
        ])

        if address_changed:
            new_city = building_data.city or building.city
            new_street = building_data.street or building.street
            new_house = building_data.house_number or building.house_number
            new_corpus = building_data.building_corpus if building_data.building_corpus is not None else building.building_corpus

            existing = await self._find_duplicate_address(
                management_company_id=management_company_id,
                city=new_city,
                street=new_street,
                house_number=new_house,
                building_corpus=new_corpus,
                exclude_id=building_id
            )

            if existing:
                raise ValueError(
                    f"Building with address '{existing.full_address}' already exists "
                    f"(ID: {existing.id})"
                )

        # Update fields
        update_data = building_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field in ['latitude', 'longitude', 'coordinates_source']:
                # Handle coordinates separately
                continue
            setattr(building, field, value)

        # Update coordinates if provided
        if 'latitude' in update_data and 'longitude' in update_data:
            if update_data['latitude'] is not None and update_data['longitude'] is not None:
                building.set_coordinates(
                    latitude=float(update_data['latitude']),
                    longitude=float(update_data['longitude']),
                    source=update_data.get('coordinates_source', 'manual')
                )

        building.updated_by = updated_by
        building.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(building)
        await self.db.commit()

        logger.info(f"Updated building {building_id}")

        return self._build_response(building)

    async def update_building_coordinates(
        self,
        building_id: UUID,
        management_company_id: UUID,
        latitude: float,
        longitude: float,
        source: str = 'google_maps'
    ) -> Optional[BuildingResponse]:
        """Update building coordinates (for geocoding service).

        Args:
            building_id: Building ID
            management_company_id: Management company ID
            latitude: Latitude
            longitude: Longitude
            source: Geocoding source (default: 'google_maps')

        Returns:
            Optional[BuildingResponse]: Updated building or None if not found
        """
        building = await self._get_building_or_none(building_id, management_company_id)
        if not building:
            return None

        building.set_coordinates(latitude, longitude, source)

        await self.db.flush()
        await self.db.refresh(building)
        await self.db.commit()

        logger.info(f"Updated coordinates for building {building_id} from {source}")

        return self._build_response(building)

    # ========================================================================
    # Delete Operations
    # ========================================================================

    async def delete_building(
        self,
        building_id: UUID,
        management_company_id: UUID,
        soft: bool = True
    ) -> bool:
        """Delete building (soft or hard delete).

        Args:
            building_id: Building ID
            management_company_id: Management company ID (tenant isolation)
            soft: If True, perform soft delete (default: True)

        Returns:
            bool: True if deleted, False if not found
        """
        # For soft delete, include already-deleted buildings (idempotent operation)
        if soft:
            query = select(Building).where(
                and_(
                    Building.id == building_id,
                    Building.management_company_id == management_company_id
                )
            )
        else:
            # For hard delete, only delete active buildings
            query = select(Building).where(
                and_(
                    Building.id == building_id,
                    Building.management_company_id == management_company_id,
                    Building.is_active == True
                )
            )

        result = await self.db.execute(query)
        building = result.scalar_one_or_none()

        if not building:
            return False

        if soft:
            # Idempotent: safe to call even if already deleted
            building.soft_delete()
            await self.db.commit()
            logger.info(f"Soft deleted building {building_id}")
        else:
            await self.db.delete(building)
            await self.db.commit()
            logger.info(f"Hard deleted building {building_id}")

        return True

    async def restore_building(
        self,
        building_id: UUID,
        management_company_id: UUID
    ) -> Optional[BuildingResponse]:
        """Restore soft-deleted building.

        Args:
            building_id: Building ID
            management_company_id: Management company ID

        Returns:
            Optional[BuildingResponse]: Restored building or None if not found
        """
        query = select(Building).where(
            and_(
                Building.id == building_id,
                Building.management_company_id == management_company_id,
                Building.is_active == False
            )
        )

        result = await self.db.execute(query)
        building = result.scalar_one_or_none()

        if not building:
            return None

        building.restore()
        await self.db.commit()

        logger.info(f"Restored building {building_id}")

        return self._build_response(building)

    # ========================================================================
    # Statistics Operations
    # ========================================================================

    async def get_statistics(
        self,
        management_company_id: UUID
    ) -> BuildingStatsResponse:
        """Get building statistics for management company.

        Args:
            management_company_id: Management company ID

        Returns:
            BuildingStatsResponse: Statistics
        """
        # Total buildings
        total_query = select(func.count()).select_from(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        )
        total_result = await self.db.execute(total_query)
        total_buildings = total_result.scalar() or 0

        # Buildings with coordinates
        with_coords_query = select(func.count()).select_from(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True,
                Building.latitude.is_not(None),
                Building.longitude.is_not(None)
            )
        )
        with_coords_result = await self.db.execute(with_coords_query)
        buildings_with_coordinates = with_coords_result.scalar() or 0

        # Buildings without coordinates
        buildings_without_coordinates = total_buildings - buildings_with_coordinates

        # Buildings by type
        by_type_query = select(
            Building.building_type,
            func.count(Building.id)
        ).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        ).group_by(Building.building_type)

        by_type_result = await self.db.execute(by_type_query)
        buildings_by_type = {
            row[0] or 'unknown': row[1]
            for row in by_type_result.all()
        }

        # Buildings by city
        by_city_query = select(
            Building.city,
            func.count(Building.id)
        ).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        ).group_by(Building.city)

        by_city_result = await self.db.execute(by_city_query)
        buildings_by_city = {
            row[0]: row[1]
            for row in by_city_result.all()
        }

        # Calculate geocoding coverage
        geocoding_coverage = (
            (buildings_with_coordinates / total_buildings * 100)
            if total_buildings > 0 else 0.0
        )

        return BuildingStatsResponse(
            total_buildings=total_buildings,
            buildings_with_coordinates=buildings_with_coordinates,
            buildings_without_coordinates=buildings_without_coordinates,
            buildings_by_type=buildings_by_type,
            buildings_by_city=buildings_by_city,
            geocoding_coverage_percent=round(geocoding_coverage, 2)
        )

    # ========================================================================
    # Geocoding Queue Operations
    # ========================================================================

    async def get_buildings_needing_geocoding(
        self,
        management_company_id: UUID,
        limit: int = 100
    ) -> List[BuildingResponse]:
        """Get buildings that need geocoding.

        Args:
            management_company_id: Management company ID
            limit: Maximum results (default: 100)

        Returns:
            List[BuildingResponse]: Buildings without coordinates
        """
        query = select(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True,
                Building.latitude.is_(None)
            )
        ).order_by(Building.created_at.asc()).limit(limit)

        result = await self.db.execute(query)
        buildings = result.scalars().all()

        return [self._build_response(b) for b in buildings]

    # ========================================================================
    # Fuzzy Matching Operations
    # ========================================================================

    async def find_similar_addresses(
        self,
        management_company_id: UUID,
        address_text: str,
        threshold: float = 0.8,
        limit: int = 10
    ) -> List[Tuple[BuildingResponse, float]]:
        """Find buildings with similar addresses using fuzzy matching.

        Args:
            management_company_id: Management company ID
            address_text: Address text to match
            threshold: Similarity threshold (0.0-1.0, default: 0.8)
            limit: Maximum results (default: 10)

        Returns:
            List[Tuple[BuildingResponse, float]]: List of (building, similarity_score)
        """
        # Get all active buildings for the management company
        query = select(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        )

        result = await self.db.execute(query)
        buildings = result.scalars().all()

        # Calculate similarity scores
        matches: List[Tuple[Building, float]] = []
        for building in buildings:
            similarity = SequenceMatcher(
                None,
                address_text.lower(),
                building.full_address.lower()
            ).ratio()

            if similarity >= threshold:
                matches.append((building, similarity))

        # Sort by similarity descending
        matches.sort(key=lambda x: x[1], reverse=True)

        # Limit results
        matches = matches[:limit]

        return [
            (self._build_response(building), score)
            for building, score in matches
        ]

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_building_or_none(
        self,
        building_id: UUID,
        management_company_id: UUID
    ) -> Optional[Building]:
        """Get building by ID with tenant isolation or return None."""
        query = select(Building).where(
            and_(
                Building.id == building_id,
                Building.management_company_id == management_company_id,
                Building.is_active == True
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _find_duplicate_address(
        self,
        management_company_id: UUID,
        city: str,
        street: str,
        house_number: str,
        building_corpus: Optional[str] = None,
        exclude_id: Optional[UUID] = None
    ) -> Optional[Building]:
        """Find building with exact same address."""
        query = select(Building).where(
            and_(
                Building.management_company_id == management_company_id,
                Building.city == city,
                Building.street == street,
                Building.house_number == house_number,
                Building.is_active == True,
                Building.deleted_at.is_(None)
            )
        )

        # Handle building_corpus (can be None)
        if building_corpus is not None:
            query = query.where(Building.building_corpus == building_corpus)
        else:
            query = query.where(Building.building_corpus.is_(None))

        # Exclude specific building ID if provided (for updates)
        if exclude_id is not None:
            query = query.where(Building.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _build_response(self, building: Building) -> BuildingResponse:
        """Build BuildingResponse from Building model."""
        return BuildingResponse(
            id=building.id,
            management_company_id=building.management_company_id,
            city=building.city,
            street=building.street,
            house_number=building.house_number,
            district=building.district,
            building_corpus=building.building_corpus,
            postal_code=building.postal_code,
            full_address=building.full_address,
            short_address=building.short_address,
            coordinates=CoordinatesResponse(
                lat=float(building.latitude),
                lon=float(building.longitude)
            ) if building.has_coordinates else None,
            coordinates_source=building.coordinates_source,
            geocoded_at=building.geocoded_at,
            building_type=building.building_type,
            floors_count=building.floors_count,
            entrance_count=building.entrance_count,
            apartments_count=building.apartments_count,
            year_built=building.year_built,
            notes=building.notes,
            extra_data=building.extra_data,
            created_at=building.created_at,
            updated_at=building.updated_at,
            is_active=building.is_active
        )
