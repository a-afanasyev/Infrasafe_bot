#!/usr/bin/env python3
"""
Data Migration Script: Populate building_id in Requests
Task 9.3 - Building Directory Integration

This script migrates existing requests to use Building Directory by:
1. Fuzzy matching addresses with buildings from Directory API
2. Auto-linking matches with >80% similarity
3. Generating report of unmatched requests for manual review
4. Supporting rollback

Usage:
    python migrate_building_ids.py --dry-run  # Preview without changes
    python migrate_building_ids.py --execute  # Execute migration
    python migrate_building_ids.py --rollback # Rollback changes
"""

import asyncio
import argparse
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional, Any
from uuid import UUID
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.request import Request
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BuildingMatcher:
    """Handles fuzzy matching of addresses with Building Directory"""

    def __init__(self, directory_api_url: str, management_company_id: str, timeout: int = 30):
        self.api_url = directory_api_url
        self.management_company_id = management_company_id
        self.timeout = timeout
        self.buildings_cache: List[Dict[str, Any]] = []

    async def load_buildings_cache(self) -> int:
        """Load all buildings from Directory API into cache"""
        try:
            headers = {
                'X-Management-Company-Id': self.management_company_id,
                'Content-Type': 'application/json'
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Fetch all buildings (paginated)
                all_buildings = []
                page = 1
                page_size = 100

                while True:
                    response = await client.get(
                        f"{self.api_url}/api/v1/buildings",
                        headers=headers,
                        params={'page': page, 'page_size': page_size, 'is_active': True}
                    )
                    response.raise_for_status()
                    data = response.json()

                    buildings = data.get('items', [])
                    if not buildings:
                        break

                    all_buildings.extend(buildings)

                    if len(buildings) < page_size:
                        break

                    page += 1

                self.buildings_cache = all_buildings
                logger.info(f"Loaded {len(self.buildings_cache)} buildings into cache")
                return len(self.buildings_cache)

        except httpx.HTTPError as e:
            logger.error(f"Failed to load buildings from Directory API: {e}")
            raise

    @staticmethod
    def normalize_address(address: str) -> str:
        """Normalize address for matching (lowercase, strip, remove punctuation)"""
        import re
        # Convert to lowercase
        normalized = address.lower()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        # Remove common punctuation
        normalized = re.sub(r'[,\.;:!?]', '', normalized)
        # Normalize common abbreviations
        replacements = {
            'г.': 'город',
            'ул.': 'улица',
            'д.': 'дом',
            'кв.': 'квартира',
            'корп.': 'корпус',
            'стр.': 'строение',
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return normalized

    def calculate_similarity(self, address1: str, address2: str) -> float:
        """Calculate similarity score between two addresses (0.0 to 1.0)"""
        norm1 = self.normalize_address(address1)
        norm2 = self.normalize_address(address2)
        return SequenceMatcher(None, norm1, norm2).ratio()

    def match_address(
        self,
        request_address: str,
        threshold: float = 0.8,
        top_n: int = 3
    ) -> Tuple[Optional[Dict[str, Any]], float, List[Tuple[Dict[str, Any], float]]]:
        """
        Match request address with buildings from cache

        Returns:
            - Best match building (if score >= threshold)
            - Best match score
            - Top N candidates with scores
        """
        if not self.buildings_cache:
            logger.warning("Buildings cache is empty")
            return None, 0.0, []

        # Calculate similarity scores for all buildings
        matches: List[Tuple[Dict[str, Any], float]] = []

        for building in self.buildings_cache:
            building_address = building.get('full_address', '')
            if not building_address:
                continue

            score = self.calculate_similarity(request_address, building_address)
            matches.append((building, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        # Get top candidates
        top_candidates = matches[:top_n]

        # Get best match if meets threshold
        if matches and matches[0][1] >= threshold:
            best_building, best_score = matches[0]
            return best_building, best_score, top_candidates

        return None, matches[0][1] if matches else 0.0, top_candidates


class MigrationStats:
    """Track migration statistics"""

    def __init__(self):
        self.total_requests = 0
        self.already_linked = 0
        self.matched = 0
        self.unmatched = 0
        self.errors = 0
        self.unmatched_requests: List[Dict[str, Any]] = []
        self.start_time = datetime.utcnow()
        self.end_time = None

    def add_unmatched(self, request_number: str, address: str, best_score: float,
                     top_candidates: List[Tuple[Dict[str, Any], float]]):
        """Add unmatched request with candidates"""
        self.unmatched_requests.append({
            'request_number': request_number,
            'address': address,
            'best_score': best_score,
            'candidates': [
                {
                    'building_id': str(candidate[0]['id']),
                    'address': candidate[0]['full_address'],
                    'score': candidate[1]
                }
                for candidate in top_candidates
            ]
        })

    def finish(self):
        """Mark migration as finished"""
        self.end_time = datetime.utcnow()

    def get_summary(self) -> Dict[str, Any]:
        """Get migration summary"""
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        match_rate = (self.matched / (self.total_requests - self.already_linked) * 100) if (self.total_requests - self.already_linked) > 0 else 0

        return {
            'total_requests': self.total_requests,
            'already_linked': self.already_linked,
            'matched': self.matched,
            'unmatched': self.unmatched,
            'errors': self.errors,
            'match_rate_percent': round(match_rate, 2),
            'duration_seconds': round(duration, 2),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None
        }

    def print_summary(self):
        """Print migration summary to console"""
        summary = self.get_summary()

        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Total Requests:        {summary['total_requests']}")
        print(f"Already Linked:        {summary['already_linked']}")
        print(f"Matched:               {summary['matched']} ✅")
        print(f"Unmatched:             {summary['unmatched']} ⚠️")
        print(f"Errors:                {summary['errors']} ❌")
        print(f"Match Rate:            {summary['match_rate_percent']}%")
        print(f"Duration:              {summary['duration_seconds']}s")
        print("="*60)

        if summary['match_rate_percent'] >= 80:
            print("✅ SUCCESS: Match rate >= 80% target")
        else:
            print(f"⚠️  WARNING: Match rate {summary['match_rate_percent']}% below 80% target")
        print()


async def migrate_requests(
    session: AsyncSession,
    matcher: BuildingMatcher,
    dry_run: bool = True,
    batch_size: int = 100,
    threshold: float = 0.8
) -> MigrationStats:
    """
    Migrate requests to use building_id from Directory

    Args:
        session: Database session
        matcher: BuildingMatcher instance
        dry_run: If True, don't commit changes
        batch_size: Number of requests to process per batch
        threshold: Minimum similarity score for auto-match
    """
    stats = MigrationStats()

    # Load buildings cache
    logger.info("Loading buildings from Directory API...")
    await matcher.load_buildings_cache()

    # Get all requests without building_id
    logger.info("Fetching requests without building_id...")
    query = select(Request).where(
        and_(
            Request.building_id == None,
            Request.is_deleted == False
        )
    )
    result = await session.execute(query)
    requests = result.scalars().all()

    stats.total_requests = len(requests)
    logger.info(f"Found {stats.total_requests} requests to migrate")

    if stats.total_requests == 0:
        logger.info("No requests to migrate")
        stats.finish()
        return stats

    # Process in batches
    for i in range(0, len(requests), batch_size):
        batch = requests[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(requests) + batch_size - 1)//batch_size} ({len(batch)} requests)")

        for request in batch:
            try:
                # Match address with buildings
                matched_building, best_score, top_candidates = matcher.match_address(
                    request.address,
                    threshold=threshold,
                    top_n=3
                )

                if matched_building:
                    # Auto-link
                    building_id = UUID(matched_building['id'])
                    building_address = matched_building['full_address']

                    logger.info(
                        f"✅ MATCH: {request.request_number} | "
                        f"Score: {best_score:.2f} | "
                        f"Building: {building_address}"
                    )

                    # Update request
                    request.building_id = building_id
                    request.building_address = building_address

                    stats.matched += 1
                else:
                    # No match found
                    logger.warning(
                        f"⚠️  NO MATCH: {request.request_number} | "
                        f"Address: {request.address} | "
                        f"Best score: {best_score:.2f}"
                    )

                    stats.add_unmatched(
                        request.request_number,
                        request.address,
                        best_score,
                        top_candidates
                    )
                    stats.unmatched += 1

            except Exception as e:
                logger.error(f"❌ ERROR processing {request.request_number}: {e}")
                stats.errors += 1

        # Commit batch if not dry run
        if not dry_run:
            await session.commit()
            logger.info(f"Committed batch {i//batch_size + 1}")
        else:
            await session.rollback()

    stats.finish()
    return stats


async def rollback_migration(session: AsyncSession) -> int:
    """Rollback migration by clearing building_id and building_address"""
    logger.info("Rolling back migration...")

    result = await session.execute(
        update(Request)
        .where(Request.building_id != None)
        .values(building_id=None, building_address=None)
    )

    count = result.rowcount
    await session.commit()

    logger.info(f"Rolled back {count} requests")
    return count


def save_unmatched_report(stats: MigrationStats, output_file: str = "unmatched_requests.json"):
    """Save unmatched requests report to JSON file"""
    report = {
        'summary': stats.get_summary(),
        'unmatched_requests': stats.unmatched_requests
    }

    output_path = Path(__file__).parent / output_file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"Unmatched report saved to {output_path}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Migrate requests to Building Directory")
    parser.add_argument(
        '--mode',
        choices=['dry-run', 'execute', 'rollback'],
        default='dry-run',
        help="Migration mode (default: dry-run)"
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.8,
        help="Minimum similarity score for auto-match (default: 0.8)"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help="Batch size for processing (default: 100)"
    )
    parser.add_argument(
        '--api-url',
        type=str,
        default=getattr(settings, 'USER_SERVICE_URL', 'http://localhost:8001'),
        help="User Service API URL"
    )
    parser.add_argument(
        '--company-id',
        type=str,
        default=getattr(settings, 'MANAGEMENT_COMPANY_ID', '00000000-0000-0000-0000-000000000001'),
        help="Management Company ID"
    )

    args = parser.parse_args()

    # Print configuration
    print("\n" + "="*60)
    print("BUILDING DIRECTORY MIGRATION")
    print("="*60)
    print(f"Mode:              {args.mode}")
    print(f"Threshold:         {args.threshold}")
    print(f"Batch Size:        {args.batch_size}")
    print(f"API URL:           {args.api_url}")
    print(f"Company ID:        {args.company_id}")
    print("="*60 + "\n")

    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            if args.mode == 'rollback':
                # Rollback migration
                count = await rollback_migration(session)
                print(f"\n✅ Rollback completed: {count} requests cleared\n")

            else:
                # Execute migration
                dry_run = (args.mode == 'dry-run')

                if dry_run:
                    print("🔍 DRY RUN MODE: No changes will be committed\n")
                else:
                    print("⚠️  EXECUTE MODE: Changes will be committed\n")

                # Create matcher
                matcher = BuildingMatcher(
                    directory_api_url=args.api_url,
                    management_company_id=args.company_id
                )

                # Run migration
                stats = await migrate_requests(
                    session=session,
                    matcher=matcher,
                    dry_run=dry_run,
                    batch_size=args.batch_size,
                    threshold=args.threshold
                )

                # Print summary
                stats.print_summary()

                # Save unmatched report
                if stats.unmatched > 0:
                    save_unmatched_report(stats)
                    print(f"📄 Unmatched report: {Path(__file__).parent / 'unmatched_requests.json'}\n")

                # Validation
                if not dry_run:
                    if stats.errors > 0:
                        print("❌ Migration completed with errors\n")
                        sys.exit(1)
                    elif stats.get_summary()['match_rate_percent'] < 80:
                        print("⚠️  Migration completed but match rate below 80% target\n")
                        sys.exit(1)
                    else:
                        print("✅ Migration completed successfully\n")
                        sys.exit(0)
                else:
                    print("ℹ️  Dry run completed - use --mode execute to apply changes\n")
                    sys.exit(0)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
