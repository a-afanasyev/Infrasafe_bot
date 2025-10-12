"""
Analytics Service - Building ETL Service
Task 10.2 - ETL Jobs for Building Directory Sync

ETL (Extract, Transform, Load) service for syncing Building Directory
to Data Warehouse dim_buildings dimension table with SCD Type 2
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.dim_building import DimBuilding

logger = logging.getLogger(__name__)


class BuildingETLService:
    """
    ETL Service for Building Directory synchronization

    Scheduled jobs:
    - Daily full sync (2 AM): Sync all buildings from Directory
    - Incremental sync (hourly): Sync recently updated buildings
    - Cleanup job (weekly): Remove obsolete records

    SCD Type 2 strategy:
    - Compare current version in warehouse with Directory
    - If changed → expire old version, insert new version
    - If unchanged → skip (no new row)
    """

    def __init__(
        self,
        session: AsyncSession,
        directory_api_url: str = "http://localhost:8001",
        management_company_id: str = "00000000-0000-0000-0000-000000000001",
        timeout: int = 30
    ):
        self.session = session
        self.directory_api_url = directory_api_url
        self.management_company_id = management_company_id
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers for Directory API"""
        return {
            'X-Management-Company-Id': self.management_company_id,
            'Content-Type': 'application/json'
        }

    async def extract_buildings_from_directory(
        self,
        page_size: int = 100,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract all buildings from Directory API (paginated)

        Args:
            page_size: Items per page
            is_active: Filter by active status (None = all)

        Returns:
            List of building dictionaries from Directory
        """
        buildings = []
        page = 1

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                while True:
                    params = {
                        'page': page,
                        'page_size': page_size
                    }
                    if is_active is not None:
                        params['is_active'] = is_active

                    response = await client.get(
                        f"{self.directory_api_url}/api/v1/buildings",
                        headers=self._get_headers(),
                        params=params
                    )
                    response.raise_for_status()
                    data = response.json()

                    items = data.get('items', [])
                    if not items:
                        break

                    buildings.extend(items)

                    # Check if more pages
                    if len(items) < page_size:
                        break

                    page += 1

            logger.info(f"Extracted {len(buildings)} buildings from Directory")
            return buildings

        except httpx.HTTPError as e:
            logger.error(f"Failed to extract buildings from Directory: {e}")
            raise

    def transform_building(self, building: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform building data from Directory format to warehouse format

        Args:
            building: Building dict from Directory API

        Returns:
            Transformed dict for dim_buildings
        """
        return {
            'building_id': UUID(building['id']),
            'management_company_id': UUID(building['management_company_id']),
            'city': building.get('city', ''),
            'district': building.get('district'),
            'street': building.get('street', ''),
            'house_number': building.get('house_number', ''),
            'building_corpus': building.get('building_corpus'),
            'full_address': building.get('full_address', ''),
            'latitude': building.get('latitude'),
            'longitude': building.get('longitude'),
            'coordinates_source': building.get('coordinates_source'),
            'building_type': building.get('building_type'),
            'floors_count': building.get('floors_count'),
            'apartments_count': building.get('apartments_count'),
            'is_active': building.get('is_active', True)
        }

    async def load_building_scd2(
        self,
        building_data: Dict[str, Any]
    ) -> Optional[int]:
        """
        Load building into warehouse using SCD Type 2 logic

        SCD Type 2 Logic:
        1. Get current version from warehouse
        2. Compare with new data
        3. If different → expire old, insert new
        4. If same → skip

        Args:
            building_data: Transformed building dict

        Returns:
            building_key of loaded record (None if skipped)
        """
        building_id = building_data['building_id']

        # Get current version from warehouse
        query = select(DimBuilding).where(
            and_(
                DimBuilding.building_id == building_id,
                DimBuilding.is_current == True
            )
        )
        result = await self.session.execute(query)
        current = result.scalar_one_or_none()

        # If no current version → INSERT new
        if not current:
            new_building = DimBuilding(
                **building_data,
                effective_from=datetime.utcnow(),
                effective_to=None,
                is_current=True
            )
            self.session.add(new_building)
            await self.session.flush()

            logger.info(f"Inserted new building: {building_id} (key={new_building.building_key})")
            return new_building.building_key

        # Check if any tracked fields changed
        has_changes = (
            current.city != building_data['city'] or
            current.district != building_data.get('district') or
            current.street != building_data['street'] or
            current.house_number != building_data['house_number'] or
            current.building_corpus != building_data.get('building_corpus') or
            current.full_address != building_data['full_address'] or
            current.latitude != building_data.get('latitude') or
            current.longitude != building_data.get('longitude') or
            current.is_active != building_data['is_active']
        )

        # If no changes → UPDATE metadata only
        if not has_changes:
            current.building_type = building_data.get('building_type')
            current.floors_count = building_data.get('floors_count')
            current.apartments_count = building_data.get('apartments_count')
            current.coordinates_source = building_data.get('coordinates_source')
            current.updated_at = datetime.utcnow()

            logger.debug(f"No changes for building: {building_id} (key={current.building_key})")
            return current.building_key

        # Changes detected → SCD Type 2 update
        # 1. Expire current version
        current.effective_to = datetime.utcnow()
        current.is_current = False
        current.updated_at = datetime.utcnow()

        # 2. Insert new version
        new_building = DimBuilding(
            **building_data,
            effective_from=datetime.utcnow(),
            effective_to=None,
            is_current=True
        )
        self.session.add(new_building)
        await self.session.flush()

        logger.info(
            f"SCD Type 2 update: {building_id} | "
            f"Old key={current.building_key} → New key={new_building.building_key}"
        )
        return new_building.building_key

    async def sync_buildings_full(self) -> Dict[str, int]:
        """
        Full sync of all buildings from Directory to warehouse

        Scheduled: Daily at 2 AM

        Returns:
            Statistics: {'extracted': N, 'inserted': M, 'updated': K, 'skipped': L}
        """
        logger.info("Starting full building sync...")
        start_time = datetime.utcnow()

        stats = {
            'extracted': 0,
            'inserted': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }

        try:
            # Extract all buildings from Directory
            buildings = await self.extract_buildings_from_directory()
            stats['extracted'] = len(buildings)

            # Transform and load each building
            for building in buildings:
                try:
                    transformed = self.transform_building(building)
                    building_key = await self.load_building_scd2(transformed)

                    if building_key:
                        # Check if it was insert or update
                        # (if key was just created, it's insert; otherwise update)
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1

                except Exception as e:
                    logger.error(f"Failed to load building {building.get('id')}: {e}")
                    stats['errors'] += 1

            # Commit transaction
            await self.session.commit()

            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"Full building sync completed in {duration:.2f}s | "
                f"Stats: {stats}"
            )

            return stats

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Full building sync failed: {e}")
            raise

    async def sync_buildings_incremental(
        self,
        since: datetime
    ) -> Dict[str, int]:
        """
        Incremental sync of recently updated buildings

        Scheduled: Hourly

        Args:
            since: Sync buildings updated after this timestamp

        Returns:
            Statistics dict
        """
        logger.info(f"Starting incremental building sync (since {since})...")

        stats = {
            'extracted': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }

        try:
            # Note: This requires Directory API to support 'updated_since' filter
            # For now, we'll do full sync with filtered processing
            buildings = await self.extract_buildings_from_directory()

            # Filter by updated_at (if available in API response)
            recent_buildings = [
                b for b in buildings
                if b.get('updated_at') and
                   datetime.fromisoformat(b['updated_at'].replace('Z', '+00:00')) > since
            ]

            stats['extracted'] = len(recent_buildings)

            for building in recent_buildings:
                try:
                    transformed = self.transform_building(building)
                    building_key = await self.load_building_scd2(transformed)

                    if building_key:
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1

                except Exception as e:
                    logger.error(f"Failed to load building {building.get('id')}: {e}")
                    stats['errors'] += 1

            await self.session.commit()

            logger.info(f"Incremental sync completed | Stats: {stats}")
            return stats

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Incremental sync failed: {e}")
            raise

    async def cleanup_obsolete_records(self, days: int = 90) -> int:
        """
        Cleanup obsolete non-current records older than N days

        Scheduled: Weekly

        Args:
            days: Keep records newer than this many days

        Returns:
            Number of deleted records
        """
        logger.info(f"Cleaning up obsolete records older than {days} days...")

        cutoff_date = datetime.utcnow()
        # Subtract days manually
        from datetime import timedelta
        cutoff_date = cutoff_date - timedelta(days=days)

        try:
            # Delete non-current records older than cutoff
            # (Keep current versions and recent history)
            result = await self.session.execute(
                select(DimBuilding).where(
                    and_(
                        DimBuilding.is_current == False,
                        DimBuilding.effective_to < cutoff_date
                    )
                )
            )
            obsolete = result.scalars().all()

            for record in obsolete:
                await self.session.delete(record)

            await self.session.commit()

            logger.info(f"Cleaned up {len(obsolete)} obsolete records")
            return len(obsolete)

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Cleanup failed: {e}")
            raise

    async def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Get current warehouse statistics

        Returns:
            Statistics about dim_buildings table
        """
        try:
            # Total buildings
            result = await self.session.execute(
                select(DimBuilding).where(DimBuilding.is_current == True)
            )
            current_count = len(result.scalars().all())

            # Historical versions count
            result = await self.session.execute(
                select(DimBuilding).where(DimBuilding.is_current == False)
            )
            historical_count = len(result.scalars().all())

            # Buildings by city
            result = await self.session.execute(
                select(DimBuilding.city, DimBuilding.building_id).where(
                    DimBuilding.is_current == True
                )
            )
            cities = {}
            for city, _ in result:
                cities[city] = cities.get(city, 0) + 1

            return {
                'current_buildings': current_count,
                'historical_versions': historical_count,
                'total_records': current_count + historical_count,
                'cities': cities
            }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
