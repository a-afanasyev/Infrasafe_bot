# Common Schemas for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

T = TypeVar('T')


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints"""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")
    sort_by: str = Field(default="created_at", description="Field to sort by")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper"""
    items: List[T] = Field(description="List of items")
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number")
    size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(description="Error type")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(default=None, description="Request ID for tracking")


class ServiceHealth(BaseModel):
    """Service health status"""
    status: str = Field(description="Health status")
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: Optional[Dict[str, Any]] = Field(default=None, description="Database health")
    dependencies: Optional[Dict[str, Any]] = Field(default=None, description="Dependency health")


class ServiceInfo(BaseModel):
    """Service information"""
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    description: str = Field(description="Service description")
    port: int = Field(description="Service port")
    environment: str = Field(description="Environment")


class CoordinatesSchema(BaseModel):
    """Geographic coordinates"""
    lat: float = Field(description="Latitude", ge=-90, le=90)
    lng: float = Field(description="Longitude", ge=-180, le=180)

    model_config = ConfigDict(from_attributes=True)


class LocationSchema(BaseModel):
    """Location information"""
    address: Optional[str] = Field(default=None, description="Street address")
    coordinates: Optional[CoordinatesSchema] = Field(default=None, description="GPS coordinates")
    city: Optional[str] = Field(default=None, description="City")
    region: Optional[str] = Field(default=None, description="Region/State")

    model_config = ConfigDict(from_attributes=True)