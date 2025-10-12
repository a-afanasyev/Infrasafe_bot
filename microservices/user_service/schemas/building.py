"""Building Pydantic Schemas for User Service - Building Directory.

Task 1.3: Create Building Pydantic Schemas (P0)
Week 1, Day 1 - Building Directory Implementation
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, computed_field, ConfigDict


# ============================================================================
# Base Schemas
# ============================================================================

class BuildingBase(BaseModel):
    """Base building schema with common fields."""

    # Address components (required)
    city: str = Field(..., min_length=1, max_length=100, description="City name")
    street: str = Field(..., min_length=1, max_length=200, description="Street name")
    house_number: str = Field(..., min_length=1, max_length=20, description="House number")

    # Address components (optional)
    district: Optional[str] = Field(None, max_length=100, description="District/neighborhood")
    building_corpus: Optional[str] = Field(None, max_length=10, description="Building corpus/section (e.g., 'A', '1')")
    postal_code: Optional[str] = Field(None, max_length=10, description="Postal/ZIP code")

    # Building extra data (optional)
    building_type: Optional[str] = Field(
        None,
        description="Type of building: residential, commercial, mixed, industrial, other"
    )
    floors_count: Optional[int] = Field(None, gt=0, description="Number of floors")
    entrance_count: Optional[int] = Field(None, gt=0, description="Number of entrances")
    apartments_count: Optional[int] = Field(None, ge=0, description="Number of apartments/units")
    year_built: Optional[int] = Field(None, ge=1800, le=2100, description="Year of construction")

    # Additional information
    notes: Optional[str] = Field(None, description="Free-form notes")
    extra_data: Optional[Dict[str, Any]] = Field(None, description="Extensible extra data field")

    @field_validator('city', 'street', 'house_number')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate required address components are not empty."""
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()

    @field_validator('building_type')
    @classmethod
    def validate_building_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate building type is one of allowed values."""
        if v is not None:
            allowed_types = {'residential', 'commercial', 'mixed', 'industrial', 'other'}
            if v not in allowed_types:
                raise ValueError(f"building_type must be one of {allowed_types}")
        return v

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Request Schemas
# ============================================================================

class BuildingCreate(BuildingBase):
    """Schema for creating a new building.

    Management company ID will be extracted from authentication context.
    Coordinates can be provided manually or left empty for geocoding.
    """

    # Optional manual coordinates
    latitude: Optional[Decimal] = Field(
        None,
        ge=Decimal('-90'),
        le=Decimal('90'),
        description="Latitude (-90 to 90)"
    )
    longitude: Optional[Decimal] = Field(
        None,
        ge=Decimal('-180'),
        le=Decimal('180'),
        description="Longitude (-180 to 180)"
    )
    coordinates_source: Optional[str] = Field(
        None,
        description="Source of coordinates: google_maps, yandex_maps, manual, 2gis, osm"
    )

    @field_validator('coordinates_source')
    @classmethod
    def validate_coordinates_source(cls, v: Optional[str]) -> Optional[str]:
        """Validate coordinates source is one of allowed values."""
        if v is not None:
            allowed_sources = {'google_maps', 'yandex_maps', 'manual', '2gis', 'osm'}
            if v not in allowed_sources:
                raise ValueError(f"coordinates_source must be one of {allowed_sources}")
        return v

    @field_validator('longitude')
    @classmethod
    def validate_coordinates_together(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        """Validate that both coordinates are provided together."""
        latitude = info.data.get('latitude')
        if (latitude is not None) != (v is not None):
            raise ValueError('Both latitude and longitude must be provided together or both omitted')
        return v


class BuildingUpdate(BaseModel):
    """Schema for updating an existing building.

    All fields are optional to support partial updates.
    """

    # Address components
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    street: Optional[str] = Field(None, min_length=1, max_length=200)
    house_number: Optional[str] = Field(None, min_length=1, max_length=20)
    district: Optional[str] = Field(None, max_length=100)
    building_corpus: Optional[str] = Field(None, max_length=10)
    postal_code: Optional[str] = Field(None, max_length=10)

    # Coordinates
    latitude: Optional[Decimal] = Field(None, ge=Decimal('-90'), le=Decimal('90'))
    longitude: Optional[Decimal] = Field(None, ge=Decimal('-180'), le=Decimal('180'))
    coordinates_source: Optional[str] = None

    # Building extra data
    building_type: Optional[str] = None
    floors_count: Optional[int] = Field(None, gt=0)
    entrance_count: Optional[int] = Field(None, gt=0)
    apartments_count: Optional[int] = Field(None, ge=0)
    year_built: Optional[int] = Field(None, ge=1800, le=2100)

    # Additional information
    notes: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

    @field_validator('building_type')
    @classmethod
    def validate_building_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate building type."""
        if v is not None:
            allowed_types = {'residential', 'commercial', 'mixed', 'industrial', 'other'}
            if v not in allowed_types:
                raise ValueError(f"building_type must be one of {allowed_types}")
        return v

    @field_validator('coordinates_source')
    @classmethod
    def validate_coordinates_source(cls, v: Optional[str]) -> Optional[str]:
        """Validate coordinates source."""
        if v is not None:
            allowed_sources = {'google_maps', 'yandex_maps', 'manual', '2gis', 'osm'}
            if v not in allowed_sources:
                raise ValueError(f"coordinates_source must be one of {allowed_sources}")
        return v

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Response Schemas
# ============================================================================

class CoordinatesResponse(BaseModel):
    """Coordinates sub-schema."""
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")

    model_config = ConfigDict(from_attributes=True)


class BuildingResponse(BuildingBase):
    """Schema for building response (read operations).

    Includes all fields from database plus computed properties.
    """

    id: UUID = Field(..., description="Building unique identifier")
    management_company_id: UUID = Field(..., description="Management company ID (tenant isolation)")

    # Computed full address
    full_address: str = Field(..., description="Full formatted address")
    short_address: str = Field(..., description="Short address without city")

    # Coordinates
    coordinates: Optional[CoordinatesResponse] = Field(None, description="Geographic coordinates")
    coordinates_source: Optional[str] = Field(None, description="Source of geocoding")
    geocoded_at: Optional[datetime] = Field(None, description="When geocoding was performed")

    # Audit fields
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    is_active: bool = Field(..., description="Active status (soft delete)")
    deleted_at: Optional[datetime] = Field(None, description="Soft delete timestamp")

    model_config = ConfigDict(from_attributes=True)


class BuildingListResponse(BaseModel):
    """Schema for paginated list of buildings."""

    items: List[BuildingResponse] = Field(..., description="List of buildings")
    total: int = Field(..., ge=0, description="Total count of buildings")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Filter Schemas
# ============================================================================

class BuildingFilter(BaseModel):
    """Schema for filtering buildings."""

    city: Optional[str] = Field(None, description="Filter by city (partial match)")
    street: Optional[str] = Field(None, description="Filter by street (partial match)")
    district: Optional[str] = Field(None, description="Filter by district")
    building_type: Optional[str] = Field(None, description="Filter by building type")
    has_coordinates: Optional[bool] = Field(None, description="Filter by coordinate presence")
    is_active: Optional[bool] = Field(True, description="Filter by active status")

    # Pagination
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")

    # Sorting
    sort_by: str = Field('created_at', description="Sort field: created_at, city, street, updated_at")
    sort_order: str = Field('desc', description="Sort order: asc, desc")

    @field_validator('sort_by')
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        """Validate sort_by field."""
        allowed_fields = {'created_at', 'updated_at', 'city', 'street', 'house_number'}
        if v not in allowed_fields:
            raise ValueError(f"sort_by must be one of {allowed_fields}")
        return v

    @field_validator('sort_order')
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        """Validate sort_order."""
        if v not in {'asc', 'desc'}:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Geocoding Schemas
# ============================================================================

class GeocodeRequest(BaseModel):
    """Request schema for manually setting building coordinates."""

    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    geocoding_source: Optional[str] = Field("manual", description="Source of coordinates")
    geocoding_accuracy: Optional[str] = Field(None, description="Accuracy level (e.g., ROOFTOP)")

    model_config = ConfigDict(from_attributes=True)


class GeocodeResponse(BaseModel):
    """Response schema for geocoding operation."""

    building_id: UUID = Field(..., description="Building ID")
    success: bool = Field(..., description="Whether geocoding was successful")
    coordinates: Optional[CoordinatesResponse] = Field(None, description="Geocoded coordinates")
    source: Optional[str] = Field(None, description="Source of geocoding")
    error: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Search Schemas
# ============================================================================

class BuildingSearchRequest(BaseModel):
    """Request schema for searching buildings."""

    query: str = Field(..., min_length=1, description="Search query (address, street, house number)")
    city: Optional[str] = Field(None, description="Filter by specific city")
    limit: int = Field(10, ge=1, le=50, description="Maximum results")

    model_config = ConfigDict(from_attributes=True)


class BuildingSearchResponse(BaseModel):
    """Response schema for building search."""

    items: List[BuildingResponse] = Field(..., description="Matched buildings")
    total: int = Field(..., ge=0, description="Total matches found")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Statistics Schemas
# ============================================================================

class BuildingStatsResponse(BaseModel):
    """Response schema for building statistics."""

    total_buildings: int = Field(..., ge=0, description="Total buildings")
    buildings_with_coordinates: int = Field(..., ge=0, description="Buildings with geocoded coordinates")
    buildings_without_coordinates: int = Field(..., ge=0, description="Buildings needing geocoding")
    buildings_by_type: Dict[str, int] = Field(..., description="Count by building type")
    buildings_by_city: Dict[str, int] = Field(..., description="Count by city")
    geocoding_coverage_percent: float = Field(..., ge=0, le=100, description="Percentage with coordinates")

    model_config = ConfigDict(from_attributes=True)
