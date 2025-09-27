"""
Request Service - Material Schemas
UK Management Bot - Request Material Management

Pydantic schemas for material operations including:
- Material CRUD operations
- Bulk material operations
- Cost calculations
- Material statistics
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field


class MaterialBase(BaseModel):
    """Base schema for material data"""
    material_name: str = Field(..., max_length=200, description="Material name")
    description: Optional[str] = Field(None, description="Material description")
    category: Optional[str] = Field(None, max_length=100, description="Material category")
    quantity: Decimal = Field(..., gt=0, description="Quantity required")
    unit: str = Field(..., max_length=20, description="Unit of measurement")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Price per unit")
    supplier: Optional[str] = Field(None, max_length=200, description="Supplier name")

    class Config:
        json_schema_extra = {
            "example": {
                "material_name": "Copper pipe 15mm",
                "description": "Copper pipe for plumbing repair",
                "category": "plumbing",
                "quantity": 5.0,
                "unit": "meters",
                "unit_price": 25.50,
                "supplier": "PlumbSupply Ltd"
            }
        }


class MaterialCreate(MaterialBase):
    """Schema for creating a new material"""
    pass


class MaterialUpdate(BaseModel):
    """Schema for updating material data"""
    material_name: Optional[str] = Field(None, max_length=200, description="Material name")
    description: Optional[str] = Field(None, description="Material description")
    category: Optional[str] = Field(None, max_length=100, description="Material category")
    quantity: Optional[Decimal] = Field(None, gt=0, description="Quantity required")
    unit: Optional[str] = Field(None, max_length=20, description="Unit of measurement")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Price per unit")
    supplier: Optional[str] = Field(None, max_length=200, description="Supplier name")
    status: Optional[str] = Field(None, description="Material status (requested/ordered/delivered/cancelled)")

    class Config:
        json_schema_extra = {
            "example": {
                "quantity": 6.0,
                "unit_price": 24.99,
                "status": "ordered"
            }
        }


class MaterialResponse(MaterialBase):
    """Response schema for material data"""
    id: str = Field(..., description="Material ID")
    request_number: str = Field(..., description="Request number")
    total_cost: Optional[Decimal] = Field(None, description="Total cost (quantity × unit_price)")
    status: str = Field(..., description="Material status")
    ordered_at: Optional[datetime] = Field(None, description="Order timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "mat_123456",
                "request_number": "250927-001",
                "material_name": "Copper pipe 15mm",
                "description": "Copper pipe for plumbing repair",
                "category": "plumbing",
                "quantity": 5.0,
                "unit": "meters",
                "unit_price": 25.50,
                "total_cost": 127.50,
                "supplier": "PlumbSupply Ltd",
                "status": "requested",
                "ordered_at": None,
                "delivered_at": None,
                "created_at": "2025-09-27T10:00:00Z",
                "updated_at": "2025-09-27T10:00:00Z"
            }
        }


class BulkMaterialRequest(BaseModel):
    """Schema for bulk material creation"""
    materials: List[MaterialCreate] = Field(..., description="List of materials to create")

    class Config:
        json_schema_extra = {
            "example": {
                "materials": [
                    {
                        "material_name": "Copper pipe 15mm",
                        "quantity": 5.0,
                        "unit": "meters",
                        "unit_price": 25.50,
                        "category": "plumbing"
                    },
                    {
                        "material_name": "Pipe fittings",
                        "quantity": 10.0,
                        "unit": "pieces",
                        "unit_price": 3.25,
                        "category": "plumbing"
                    }
                ]
            }
        }


class BulkMaterialResponse(BaseModel):
    """Response schema for bulk material operation"""
    total_materials: int = Field(..., description="Total number of materials processed")
    successful_count: int = Field(..., description="Number of successfully created materials")
    failed_count: int = Field(..., description="Number of failed material creations")
    successful_materials: List[MaterialResponse] = Field(..., description="Successfully created materials")
    failed_materials: List[Dict[str, Any]] = Field(..., description="Failed materials with error details")

    class Config:
        json_schema_extra = {
            "example": {
                "total_materials": 2,
                "successful_count": 2,
                "failed_count": 0,
                "successful_materials": [
                    {
                        "id": "mat_123456",
                        "material_name": "Copper pipe 15mm",
                        "quantity": 5.0,
                        "unit": "meters",
                        "total_cost": 127.50,
                        "status": "requested"
                    }
                ],
                "failed_materials": []
            }
        }


class MaterialCostSummary(BaseModel):
    """Cost summary for request materials"""
    request_number: str = Field(..., description="Request number")
    total_materials: int = Field(..., description="Total number of materials")
    total_estimated_cost: float = Field(..., description="Total estimated cost")
    total_ordered_cost: float = Field(..., description="Cost of ordered materials")
    total_delivered_cost: float = Field(..., description="Cost of delivered materials")
    ordered_materials: int = Field(..., description="Number of ordered materials")
    delivered_materials: int = Field(..., description="Number of delivered materials")
    pending_materials: int = Field(..., description="Number of pending materials")

    class Config:
        json_schema_extra = {
            "example": {
                "request_number": "250927-001",
                "total_materials": 5,
                "total_estimated_cost": 450.75,
                "total_ordered_cost": 275.50,
                "total_delivered_cost": 125.25,
                "ordered_materials": 3,
                "delivered_materials": 1,
                "pending_materials": 1
            }
        }


class MaterialStats(BaseModel):
    """Material statistics"""
    total_materials: int = Field(..., description="Total number of materials")
    total_cost: float = Field(..., description="Total cost of all materials")
    average_cost: float = Field(..., description="Average cost per material")
    by_status: Dict[str, int] = Field(..., description="Materials count by status")
    by_category: Dict[str, int] = Field(..., description="Materials count by category")
    period_days: int = Field(..., description="Analysis period in days")

    class Config:
        json_schema_extra = {
            "example": {
                "total_materials": 150,
                "total_cost": 12500.75,
                "average_cost": 83.34,
                "by_status": {
                    "requested": 45,
                    "ordered": 65,
                    "delivered": 35,
                    "cancelled": 5
                },
                "by_category": {
                    "plumbing": 80,
                    "electrical": 35,
                    "tools": 20,
                    "other": 15
                },
                "period_days": 30
            }
        }


class MaterialFilters(BaseModel):
    """Filters for material queries"""
    category: Optional[str] = Field(None, description="Filter by category")
    status: Optional[str] = Field(None, description="Filter by status")
    supplier: Optional[str] = Field(None, description="Filter by supplier")
    min_cost: Optional[Decimal] = Field(None, ge=0, description="Minimum cost filter")
    max_cost: Optional[Decimal] = Field(None, ge=0, description="Maximum cost filter")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "plumbing",
                "status": "ordered",
                "min_cost": 10.0,
                "max_cost": 100.0
            }
        }