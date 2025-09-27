"""
Request Service - Material Service
UK Management Bot - Request Material Management

Business logic for request material operations including:
- Material CRUD operations
- Cost calculation and tracking
- Supplier management
- Material procurement workflow
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload

from app.models import Request, RequestMaterial
from app.schemas import (
    MaterialCreate, MaterialUpdate, MaterialResponse,
    BulkMaterialRequest, BulkMaterialResponse,
    MaterialCostSummary, MaterialStats
)

logger = logging.getLogger(__name__)


class MaterialService:
    """
    Material Service handles all request material operations

    Features:
    - Material CRUD operations
    - Cost calculation and tracking
    - Bulk material operations
    - Supplier management
    - Material procurement workflow
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def create_material(
        self,
        db: AsyncSession,
        request_number: str,
        material_data: MaterialCreate,
        created_by: int
    ) -> MaterialResponse:
        """
        Create a new material for a request

        Args:
            db: Database session
            request_number: Request number to add material to
            material_data: Material details
            created_by: User ID creating the material

        Returns:
            MaterialResponse with created material details

        Raises:
            HTTPException: If request not found or creation fails
        """
        try:
            # Verify request exists
            query = select(Request).where(Request.request_number == request_number)
            result = await db.execute(query)
            request = result.scalar_one_or_none()

            if not request:
                raise ValueError(f"Request {request_number} not found")

            # Calculate total cost if unit price provided
            total_cost = None
            if material_data.unit_price:
                total_cost = material_data.quantity * material_data.unit_price

            # Create material record
            material = RequestMaterial(
                request_number=request_number,
                material_name=material_data.material_name,
                description=material_data.description,
                category=material_data.category,
                quantity=material_data.quantity,
                unit=material_data.unit,
                unit_price=material_data.unit_price,
                total_cost=total_cost,
                supplier=material_data.supplier,
                status="requested",
                created_at=datetime.utcnow()
            )

            db.add(material)
            await db.commit()
            await db.refresh(material)

            # Update request materials flag
            await self._update_request_materials_info(db, request_number)

            self.logger.info(
                f"Material '{material_data.material_name}' created for request {request_number} "
                f"by user {created_by}"
            )

            return MaterialResponse.from_orm(material)

        except Exception as e:
            await db.rollback()
            self.logger.error(f"Error creating material for request {request_number}: {str(e)}")
            raise

    async def get_material(
        self,
        db: AsyncSession,
        material_id: str
    ) -> Optional[MaterialResponse]:
        """
        Get material by ID

        Args:
            db: Database session
            material_id: Material ID to retrieve

        Returns:
            MaterialResponse or None if not found
        """
        try:
            query = select(RequestMaterial).where(RequestMaterial.id == material_id)
            result = await db.execute(query)
            material = result.scalar_one_or_none()

            return MaterialResponse.from_orm(material) if material else None

        except Exception as e:
            self.logger.error(f"Error getting material {material_id}: {str(e)}")
            raise

    async def get_materials_for_request(
        self,
        db: AsyncSession,
        request_number: str
    ) -> List[MaterialResponse]:
        """
        Get all materials for a request

        Args:
            db: Database session
            request_number: Request number

        Returns:
            List of MaterialResponse objects
        """
        try:
            query = select(RequestMaterial).where(
                RequestMaterial.request_number == request_number
            ).order_by(RequestMaterial.created_at)

            result = await db.execute(query)
            materials = result.scalars().all()

            return [MaterialResponse.from_orm(material) for material in materials]

        except Exception as e:
            self.logger.error(f"Error getting materials for request {request_number}: {str(e)}")
            raise

    async def update_material(
        self,
        db: AsyncSession,
        material_id: str,
        material_data: MaterialUpdate,
        updated_by: int
    ) -> MaterialResponse:
        """
        Update material details

        Args:
            db: Database session
            material_id: Material ID to update
            material_data: Updated material data
            updated_by: User ID making the update

        Returns:
            MaterialResponse with updated details

        Raises:
            ValueError: If material not found
        """
        try:
            query = select(RequestMaterial).where(RequestMaterial.id == material_id)
            result = await db.execute(query)
            material = result.scalar_one_or_none()

            if not material:
                raise ValueError(f"Material {material_id} not found")

            # Update fields if provided
            if material_data.material_name is not None:
                material.material_name = material_data.material_name
            if material_data.description is not None:
                material.description = material_data.description
            if material_data.category is not None:
                material.category = material_data.category
            if material_data.quantity is not None:
                material.quantity = material_data.quantity
            if material_data.unit is not None:
                material.unit = material_data.unit
            if material_data.unit_price is not None:
                material.unit_price = material_data.unit_price
            if material_data.supplier is not None:
                material.supplier = material_data.supplier
            if material_data.status is not None:
                material.status = material_data.status

            # Recalculate total cost
            if material.unit_price and material.quantity:
                material.total_cost = material.quantity * material.unit_price

            # Update timestamps
            material.updated_at = datetime.utcnow()

            # Handle status-specific updates
            if material_data.status == "ordered" and not material.ordered_at:
                material.ordered_at = datetime.utcnow()
            elif material_data.status == "delivered" and not material.delivered_at:
                material.delivered_at = datetime.utcnow()

            await db.commit()
            await db.refresh(material)

            # Update request materials info
            await self._update_request_materials_info(db, material.request_number)

            self.logger.info(f"Material {material_id} updated by user {updated_by}")

            return MaterialResponse.from_orm(material)

        except Exception as e:
            await db.rollback()
            self.logger.error(f"Error updating material {material_id}: {str(e)}")
            raise

    async def delete_material(
        self,
        db: AsyncSession,
        material_id: str,
        deleted_by: int
    ) -> bool:
        """
        Delete a material

        Args:
            db: Database session
            material_id: Material ID to delete
            deleted_by: User ID performing deletion

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If material not found
        """
        try:
            query = select(RequestMaterial).where(RequestMaterial.id == material_id)
            result = await db.execute(query)
            material = result.scalar_one_or_none()

            if not material:
                raise ValueError(f"Material {material_id} not found")

            request_number = material.request_number
            await db.delete(material)
            await db.commit()

            # Update request materials info
            await self._update_request_materials_info(db, request_number)

            self.logger.info(f"Material {material_id} deleted by user {deleted_by}")
            return True

        except Exception as e:
            await db.rollback()
            self.logger.error(f"Error deleting material {material_id}: {str(e)}")
            raise

    async def bulk_add_materials(
        self,
        db: AsyncSession,
        request_number: str,
        bulk_request: BulkMaterialRequest,
        created_by: int
    ) -> BulkMaterialResponse:
        """
        Add multiple materials in bulk operation

        Args:
            db: Database session
            request_number: Request to add materials to
            bulk_request: Bulk materials data
            created_by: User creating the materials

        Returns:
            BulkMaterialResponse with results
        """
        successful_materials = []
        failed_materials = []

        for material_item in bulk_request.materials:
            try:
                result = await self.create_material(
                    db, request_number, material_item, created_by
                )
                successful_materials.append(result)

            except Exception as e:
                failed_materials.append({
                    "material_name": material_item.material_name,
                    "error": str(e)
                })

        return BulkMaterialResponse(
            total_materials=len(bulk_request.materials),
            successful_count=len(successful_materials),
            failed_count=len(failed_materials),
            successful_materials=successful_materials,
            failed_materials=failed_materials
        )

    async def get_cost_summary(
        self,
        db: AsyncSession,
        request_number: str
    ) -> MaterialCostSummary:
        """
        Calculate cost summary for request materials

        Args:
            db: Database session
            request_number: Request number

        Returns:
            MaterialCostSummary with cost breakdown
        """
        try:
            # Get all materials for request
            query = select(RequestMaterial).where(
                RequestMaterial.request_number == request_number
            )
            result = await db.execute(query)
            materials = result.scalars().all()

            # Calculate costs
            total_cost = Decimal('0.00')
            estimated_cost = Decimal('0.00')
            ordered_cost = Decimal('0.00')
            delivered_cost = Decimal('0.00')

            materials_count = len(materials)
            ordered_count = 0
            delivered_count = 0

            for material in materials:
                if material.total_cost:
                    total_cost += material.total_cost
                    estimated_cost += material.total_cost

                    if material.status == "ordered":
                        ordered_cost += material.total_cost
                        ordered_count += 1
                    elif material.status == "delivered":
                        delivered_cost += material.total_cost
                        delivered_count += 1

            return MaterialCostSummary(
                request_number=request_number,
                total_materials=materials_count,
                total_estimated_cost=float(estimated_cost),
                total_ordered_cost=float(ordered_cost),
                total_delivered_cost=float(delivered_cost),
                ordered_materials=ordered_count,
                delivered_materials=delivered_count,
                pending_materials=materials_count - ordered_count - delivered_count
            )

        except Exception as e:
            self.logger.error(f"Error calculating cost summary for {request_number}: {str(e)}")
            raise

    async def get_material_stats(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> MaterialStats:
        """
        Get material statistics for the last N days

        Args:
            db: Database session
            days: Number of days to analyze

        Returns:
            MaterialStats with statistics
        """
        try:
            end_date = datetime.utcnow()
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = start_date - timedelta(days=days)

            # Base query for the period
            base_query = select(RequestMaterial).where(
                RequestMaterial.created_at >= start_date
            )

            # Total materials count
            total_result = await db.execute(
                select(func.count()).select_from(base_query.subquery())
            )
            total_materials = total_result.scalar()

            # Cost statistics
            cost_query = select(
                func.sum(RequestMaterial.total_cost),
                func.avg(RequestMaterial.total_cost)
            ).where(
                and_(
                    RequestMaterial.created_at >= start_date,
                    RequestMaterial.total_cost.isnot(None)
                )
            )
            cost_result = await db.execute(cost_query)
            cost_data = cost_result.fetchone()
            total_cost = float(cost_data[0]) if cost_data[0] else 0.0
            avg_cost = float(cost_data[1]) if cost_data[1] else 0.0

            # Status distribution
            status_query = select(
                RequestMaterial.status,
                func.count(RequestMaterial.id)
            ).where(
                RequestMaterial.created_at >= start_date
            ).group_by(RequestMaterial.status)

            status_result = await db.execute(status_query)
            by_status = {row[0]: row[1] for row in status_result.fetchall()}

            # Category distribution
            category_query = select(
                RequestMaterial.category,
                func.count(RequestMaterial.id)
            ).where(
                and_(
                    RequestMaterial.created_at >= start_date,
                    RequestMaterial.category.isnot(None)
                )
            ).group_by(RequestMaterial.category)

            category_result = await db.execute(category_query)
            by_category = {row[0]: row[1] for row in category_result.fetchall()}

            return MaterialStats(
                total_materials=total_materials,
                total_cost=total_cost,
                average_cost=avg_cost,
                by_status=by_status,
                by_category=by_category,
                period_days=days
            )

        except Exception as e:
            self.logger.error(f"Error getting material statistics: {str(e)}")
            raise

    async def _update_request_materials_info(
        self,
        db: AsyncSession,
        request_number: str
    ) -> None:
        """
        Update request materials information

        Args:
            db: Database session
            request_number: Request to update
        """
        try:
            # Get request
            request_query = select(Request).where(Request.request_number == request_number)
            request_result = await db.execute(request_query)
            request = request_result.scalar_one_or_none()

            if not request:
                return

            # Get materials summary
            materials_query = select(
                func.count(RequestMaterial.id),
                func.sum(RequestMaterial.total_cost)
            ).where(RequestMaterial.request_number == request_number)

            materials_result = await db.execute(materials_query)
            materials_data = materials_result.fetchone()

            materials_count = materials_data[0] if materials_data[0] else 0
            total_cost = materials_data[1] if materials_data[1] else Decimal('0.00')

            # Update request
            request.materials_requested = materials_count > 0
            request.materials_cost = total_cost

            await db.commit()

        except Exception as e:
            self.logger.error(f"Error updating request materials info: {str(e)}")
            # Don't raise, this is a background update


# Import timedelta for statistics
from datetime import timedelta

# Global material service instance
material_service = MaterialService()