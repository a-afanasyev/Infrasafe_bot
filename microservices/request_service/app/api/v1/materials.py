"""
Request Service - Materials API Endpoints
UK Management Bot - Request Material Management

REST API endpoints for request material operations including:
- Material CRUD operations
- Bulk material operations
- Cost calculations and summaries
- Material statistics and reporting
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.schemas import (
    MaterialCreate, MaterialUpdate, MaterialResponse,
    BulkMaterialRequest, BulkMaterialResponse,
    MaterialCostSummary, MaterialStats, MaterialFilters,
    ErrorResponse
)
from app.services.material_service import material_service
from app.core.auth import require_service_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("/requests/{request_number}", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
async def create_material(
    request_number: str,
    material_data: MaterialCreate,
    created_by: int = Query(..., description="User ID creating the material"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Create a new material for a request

    - Adds material to request
    - Calculates total cost automatically
    - Updates request materials information
    - Creates audit trail
    """
    try:
        result = await material_service.create_material(
            db, request_number, material_data, created_by
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating material for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error creating material"
        )


@router.get("/requests/{request_number}", response_model=List[MaterialResponse])
async def get_materials_for_request(
    request_number: str,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get all materials for a request

    - Returns all materials associated with request
    - Includes cost calculations
    - Ordered by creation date
    """
    try:
        materials = await material_service.get_materials_for_request(db, request_number)
        return materials

    except Exception as e:
        logger.error(f"Error getting materials for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting materials"
        )


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: str,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get material by ID

    - Returns detailed material information
    - Includes cost and procurement details
    - Shows current status
    """
    try:
        material = await material_service.get_material(db, material_id)

        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material {material_id} not found"
            )

        return material

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting material {material_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting material"
        )


@router.put("/{material_id}", response_model=MaterialResponse)
async def update_material(
    material_id: str,
    material_data: MaterialUpdate,
    updated_by: int = Query(..., description="User ID making the update"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Update material details

    - Updates material information
    - Recalculates costs automatically
    - Tracks status changes
    - Updates procurement timestamps
    """
    try:
        result = await material_service.update_material(
            db, material_id, material_data, updated_by
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating material {material_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating material"
        )


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: str,
    deleted_by: int = Query(..., description="User ID performing deletion"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Delete a material

    - Removes material from request
    - Updates request cost calculations
    - Creates audit trail
    """
    try:
        await material_service.delete_material(db, material_id, deleted_by)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting material {material_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error deleting material"
        )


@router.post("/requests/{request_number}/bulk", response_model=BulkMaterialResponse)
async def bulk_add_materials(
    request_number: str,
    bulk_request: BulkMaterialRequest,
    created_by: int = Query(..., description="User ID creating the materials"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Add multiple materials in bulk operation

    - Processes multiple materials in one operation
    - Returns detailed results for each material
    - Handles partial failures gracefully
    - Provides summary statistics
    """
    try:
        result = await material_service.bulk_add_materials(
            db, request_number, bulk_request, created_by
        )
        return result

    except Exception as e:
        logger.error(f"Error in bulk material creation for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error in bulk material creation"
        )


@router.get("/requests/{request_number}/cost-summary", response_model=MaterialCostSummary)
async def get_cost_summary(
    request_number: str,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get cost summary for request materials

    - Total estimated costs
    - Breakdown by status (ordered/delivered)
    - Material counts by status
    - Cost tracking across procurement lifecycle
    """
    try:
        summary = await material_service.get_cost_summary(db, request_number)
        return summary

    except Exception as e:
        logger.error(f"Error getting cost summary for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting cost summary"
        )


@router.get("/stats", response_model=MaterialStats)
async def get_material_statistics(
    days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get material statistics for specified period

    - Total materials and costs
    - Distribution by status and category
    - Average cost calculations
    - Trend analysis data
    """
    try:
        stats = await material_service.get_material_stats(db, days)
        return stats

    except Exception as e:
        logger.error(f"Error getting material statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting statistics"
        )


# Additional endpoints for request integration

@router.put("/requests/{request_number}/materials", response_model=List[MaterialResponse])
async def update_request_materials(
    request_number: str,
    materials: List[MaterialCreate],
    updated_by: int = Query(..., description="User ID making the update"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Update all materials for a request (replaces existing)

    - Replaces all existing materials with new list
    - Maintains cost calculations
    - Creates complete audit trail
    - Used for bulk material updates
    """
    try:
        # Get existing materials
        existing_materials = await material_service.get_materials_for_request(db, request_number)

        # Delete existing materials
        for material in existing_materials:
            await material_service.delete_material(db, material.id, updated_by)

        # Create new materials
        bulk_request = BulkMaterialRequest(materials=materials)
        result = await material_service.bulk_add_materials(
            db, request_number, bulk_request, updated_by
        )

        return result.successful_materials

    except Exception as e:
        logger.error(f"Error updating materials for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating materials"
        )


@router.post("/{material_id}/order")
async def order_material(
    material_id: str,
    ordered_by: int = Query(..., description="User ID ordering the material"),
    supplier: Optional[str] = Query(None, description="Supplier for this order"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Mark material as ordered

    - Updates status to 'ordered'
    - Sets order timestamp
    - Updates supplier if provided
    - Triggers procurement workflow
    """
    try:
        update_data = MaterialUpdate(
            status="ordered",
            supplier=supplier
        )

        result = await material_service.update_material(
            db, material_id, update_data, ordered_by
        )

        return {
            "message": f"Material {material_id} marked as ordered",
            "material": result
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error ordering material {material_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error ordering material"
        )


@router.post("/{material_id}/deliver")
async def deliver_material(
    material_id: str,
    delivered_by: int = Query(..., description="User ID confirming delivery"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Mark material as delivered

    - Updates status to 'delivered'
    - Sets delivery timestamp
    - Completes procurement workflow
    - Updates request cost tracking
    """
    try:
        update_data = MaterialUpdate(status="delivered")

        result = await material_service.update_material(
            db, material_id, update_data, delivered_by
        )

        return {
            "message": f"Material {material_id} marked as delivered",
            "material": result
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error delivering material {material_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error delivering material"
        )