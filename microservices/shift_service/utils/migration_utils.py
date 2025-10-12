# Data Migration Utilities for Shift Service
# UK Management Bot - Shift Service

import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID, uuid4

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal, execute_migration_batch

logger = logging.getLogger(__name__)


class DataMigrationService:
    """
    Service for handling data migration from monolith to Shift Service
    Implements safe migration with rollback capabilities
    """

    def __init__(self):
        self.batch_size = settings.migration_batch_size
        self.timeout_minutes = settings.migration_timeout_minutes

    async def migrate_shifts_from_monolith(
        self,
        source_connection_string: str,
        validation_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Migrate shifts data from monolith database to Shift Service

        Args:
            source_connection_string: Connection string to monolith database
            validation_mode: If True, only validate without actual migration

        Returns:
            Migration report with statistics and any errors
        """
        logger.info(f"Starting shifts migration (validation_mode={validation_mode})")

        migration_report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "validation_mode": validation_mode,
            "total_records": 0,
            "migrated_records": 0,
            "failed_records": 0,
            "errors": [],
            "rollback_data_file": None,
            "completed_at": None
        }

        try:
            # Create rollback data file for safety
            rollback_file = await self._create_rollback_file("shifts_migration")
            migration_report["rollback_data_file"] = rollback_file

            # Connect to source database
            source_conn = await asyncpg.connect(source_connection_string)

            try:
                # Extract shifts data from monolith
                shifts_data = await self._extract_shifts_from_monolith(source_conn)
                migration_report["total_records"] = len(shifts_data)

                if not validation_mode:
                    # Perform actual migration
                    async with AsyncSessionLocal() as db:
                        migrated_count = await self._migrate_shifts_batch(
                            db, shifts_data, rollback_file
                        )
                        migration_report["migrated_records"] = migrated_count

                else:
                    # Validation only
                    validation_errors = await self._validate_shifts_data(shifts_data)
                    migration_report["errors"].extend(validation_errors)
                    migration_report["migrated_records"] = 0

            finally:
                await source_conn.close()

        except Exception as e:
            error_msg = f"Migration failed: {e}"
            logger.error(error_msg)
            migration_report["errors"].append(error_msg)

        finally:
            migration_report["completed_at"] = datetime.now(timezone.utc).isoformat()
            migration_report["failed_records"] = (
                migration_report["total_records"] - migration_report["migrated_records"]
            )

        logger.info(f"Migration completed: {migration_report}")
        return migration_report

    async def rollback_migration(self, rollback_file: str) -> Dict[str, Any]:
        """
        Rollback a migration using the rollback data file

        Args:
            rollback_file: Path to the rollback data file

        Returns:
            Rollback report with statistics
        """
        logger.info(f"Starting migration rollback from file: {rollback_file}")

        rollback_report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "rollback_file": rollback_file,
            "records_processed": 0,
            "records_deleted": 0,
            "errors": [],
            "completed_at": None
        }

        try:
            # Load rollback data
            rollback_data = await self._load_rollback_data(rollback_file)
            rollback_report["records_processed"] = len(rollback_data)

            # Perform rollback
            async with AsyncSessionLocal() as db:
                deleted_count = await self._execute_rollback(db, rollback_data)
                rollback_report["records_deleted"] = deleted_count

        except Exception as e:
            error_msg = f"Rollback failed: {e}"
            logger.error(error_msg)
            rollback_report["errors"].append(error_msg)

        finally:
            rollback_report["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(f"Rollback completed: {rollback_report}")
        return rollback_report

    async def _extract_shifts_from_monolith(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Extract shifts data from monolith database"""
        try:
            # Query to extract shifts from monolith
            # This assumes the monolith has a 'shifts' table with similar structure
            query = """
            SELECT
                id,
                title,
                description,
                start_time,
                end_time,
                status,
                shift_type,
                executor_id,
                specialization,
                location,
                coordinates,
                address,
                requirements,
                priority,
                template_id,
                created_at,
                updated_at,
                created_by,
                completion_rating,
                actual_duration_hours,
                efficiency_score
            FROM shifts
            WHERE created_at >= NOW() - INTERVAL '1 year'
            ORDER BY created_at
            """

            rows = await conn.fetch(query)

            shifts_data = []
            for row in rows:
                shift_data = {
                    "original_id": str(row["id"]),
                    "title": row["title"],
                    "description": row["description"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "status": row["status"],
                    "shift_type": row.get("shift_type", "regular"),
                    "executor_id": str(row["executor_id"]) if row["executor_id"] else None,
                    "specialization": row["specialization"],
                    "location": row["location"],
                    "coordinates": json.loads(row["coordinates"]) if row["coordinates"] else None,
                    "address": row["address"],
                    "requirements": json.loads(row["requirements"]) if row["requirements"] else None,
                    "priority": row.get("priority", 1),
                    "template_id": str(row["template_id"]) if row.get("template_id") else None,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "created_by": str(row["created_by"]),
                    "completion_rating": row.get("completion_rating"),
                    "actual_duration_hours": row.get("actual_duration_hours"),
                    "efficiency_score": row.get("efficiency_score")
                }
                shifts_data.append(shift_data)

            logger.info(f"Extracted {len(shifts_data)} shifts from monolith")
            return shifts_data

        except Exception as e:
            logger.error(f"Failed to extract shifts from monolith: {e}")
            raise

    async def _validate_shifts_data(self, shifts_data: List[Dict[str, Any]]) -> List[str]:
        """Validate shifts data before migration"""
        errors = []

        for i, shift in enumerate(shifts_data):
            try:
                # Validate required fields
                if not shift.get("title"):
                    errors.append(f"Shift {i}: Missing title")

                if not shift.get("start_time") or not shift.get("end_time"):
                    errors.append(f"Shift {i}: Missing start_time or end_time")

                if not shift.get("specialization"):
                    errors.append(f"Shift {i}: Missing specialization")

                if not shift.get("created_by"):
                    errors.append(f"Shift {i}: Missing created_by")

                # Validate time logic
                if shift.get("start_time") and shift.get("end_time"):
                    if shift["start_time"] >= shift["end_time"]:
                        errors.append(f"Shift {i}: start_time must be before end_time")

                # Validate UUIDs
                if shift.get("executor_id"):
                    try:
                        UUID(shift["executor_id"])
                    except ValueError:
                        errors.append(f"Shift {i}: Invalid executor_id UUID")

                if shift.get("created_by"):
                    try:
                        UUID(shift["created_by"])
                    except ValueError:
                        errors.append(f"Shift {i}: Invalid created_by UUID")

            except Exception as e:
                errors.append(f"Shift {i}: Validation error - {e}")

        return errors

    async def _migrate_shifts_batch(
        self,
        db: AsyncSession,
        shifts_data: List[Dict[str, Any]],
        rollback_file: str
    ) -> int:
        """Migrate shifts data in batches"""
        migrated_count = 0
        rollback_records = []

        try:
            for i in range(0, len(shifts_data), self.batch_size):
                batch = shifts_data[i:i + self.batch_size]

                # Process each shift in the batch
                for shift_data in batch:
                    try:
                        # Generate new UUID for the shift
                        new_shift_id = uuid4()

                        # Calculate duration
                        duration = (
                            shift_data["end_time"] - shift_data["start_time"]
                        ).total_seconds() / 3600

                        # Prepare insert query
                        insert_query = """
                        INSERT INTO shifts (
                            id, title, description, start_time, end_time, duration_hours,
                            status, shift_type, executor_id, specialization, location,
                            coordinates, address, requirements, priority, template_id,
                            created_at, updated_at, created_by, completion_rating,
                            actual_duration_hours, efficiency_score
                        ) VALUES (
                            :id, :title, :description, :start_time, :end_time, :duration_hours,
                            :status, :shift_type, :executor_id, :specialization, :location,
                            :coordinates, :address, :requirements, :priority, :template_id,
                            :created_at, :updated_at, :created_by, :completion_rating,
                            :actual_duration_hours, :efficiency_score
                        )
                        """

                        values = {
                            "id": str(new_shift_id),
                            "title": shift_data["title"],
                            "description": shift_data.get("description"),
                            "start_time": shift_data["start_time"],
                            "end_time": shift_data["end_time"],
                            "duration_hours": duration,
                            "status": shift_data.get("status", "planned"),
                            "shift_type": shift_data.get("shift_type", "regular"),
                            "executor_id": shift_data.get("executor_id"),
                            "specialization": shift_data["specialization"],
                            "location": shift_data.get("location"),
                            "coordinates": json.dumps(shift_data.get("coordinates")),
                            "address": shift_data.get("address"),
                            "requirements": json.dumps(shift_data.get("requirements")),
                            "priority": shift_data.get("priority", 1),
                            "template_id": shift_data.get("template_id"),
                            "created_at": shift_data["created_at"],
                            "updated_at": shift_data.get("updated_at", shift_data["created_at"]),
                            "created_by": shift_data["created_by"],
                            "completion_rating": shift_data.get("completion_rating"),
                            "actual_duration_hours": shift_data.get("actual_duration_hours"),
                            "efficiency_score": shift_data.get("efficiency_score")
                        }

                        await db.execute(text(insert_query), values)

                        # Add to rollback data
                        rollback_records.append({
                            "operation": "insert",
                            "table": "shifts",
                            "new_id": str(new_shift_id),
                            "original_id": shift_data["original_id"]
                        })

                        migrated_count += 1

                    except Exception as e:
                        logger.error(f"Failed to migrate shift {shift_data.get('original_id')}: {e}")

                # Commit batch
                await db.commit()
                logger.info(f"Migrated batch: {migrated_count}/{len(shifts_data)} shifts")

            # Save rollback data
            await self._save_rollback_data(rollback_file, rollback_records)

            return migrated_count

        except Exception as e:
            await db.rollback()
            logger.error(f"Batch migration failed: {e}")
            raise

    async def _create_rollback_file(self, migration_name: str) -> str:
        """Create a rollback data file"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"rollback_{migration_name}_{timestamp}.json"
        return filename

    async def _save_rollback_data(self, filename: str, rollback_data: List[Dict[str, Any]]):
        """Save rollback data to file"""
        try:
            import aiofiles

            async with aiofiles.open(filename, 'w') as f:
                await f.write(json.dumps(rollback_data, indent=2, default=str))

            logger.info(f"Saved rollback data to {filename}")

        except Exception as e:
            logger.error(f"Failed to save rollback data: {e}")

    async def _load_rollback_data(self, filename: str) -> List[Dict[str, Any]]:
        """Load rollback data from file"""
        try:
            import aiofiles

            async with aiofiles.open(filename, 'r') as f:
                content = await f.read()
                return json.loads(content)

        except Exception as e:
            logger.error(f"Failed to load rollback data: {e}")
            raise

    async def _execute_rollback(self, db: AsyncSession, rollback_data: List[Dict[str, Any]]) -> int:
        """Execute rollback operations"""
        deleted_count = 0

        try:
            for record in rollback_data:
                if record["operation"] == "insert":
                    # Delete the inserted record
                    delete_query = f"DELETE FROM {record['table']} WHERE id = :id"
                    await db.execute(text(delete_query), {"id": record["new_id"]})
                    deleted_count += 1

            await db.commit()
            return deleted_count

        except Exception as e:
            await db.rollback()
            logger.error(f"Rollback execution failed: {e}")
            raise


# CLI Functions for manual migration management

async def validate_migration_data(source_connection_string: str) -> Dict[str, Any]:
    """Validate migration data without performing migration"""
    service = DataMigrationService()
    return await service.migrate_shifts_from_monolith(
        source_connection_string, validation_mode=True
    )


async def execute_migration(source_connection_string: str) -> Dict[str, Any]:
    """Execute full migration"""
    service = DataMigrationService()
    return await service.migrate_shifts_from_monolith(
        source_connection_string, validation_mode=False
    )


async def rollback_migration(rollback_file: str) -> Dict[str, Any]:
    """Rollback migration using rollback file"""
    service = DataMigrationService()
    return await service.rollback_migration(rollback_file)