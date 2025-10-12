"""Building Model for User Service - Building Directory.

Task 1.2: Create Building SQLAlchemy Model (P0)
Week 1, Day 1 - Building Directory Implementation
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from decimal import Decimal

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Text, Numeric,
    ForeignKey, CheckConstraint, Index, event, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import validates, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from .user import Base


class Building(Base):
    """Building model for centralized building directory.

    This model represents a building managed by a property management company (УК).
    Each building has a unique address within a management company and can be
    associated with multiple requests.

    Attributes:
        id: Unique building identifier (UUID)
        management_company_id: Tenant isolation - which УК owns this building
        city: City name (required)
        street: Street name (required)
        house_number: House number (required)
        district: District/neighborhood (optional)
        building_corpus: Building corpus/section (optional, e.g., "A", "1")
        postal_code: Postal/ZIP code (optional)
        latitude: Geocoded latitude (-90 to 90)
        longitude: Geocoded longitude (-180 to 180)
        coordinates_source: Source of geocoding ('google_maps', 'manual', 'yandex_maps')
        geocoded_at: When geocoding was performed
        building_type: Type of building ('residential', 'commercial', 'mixed')
        floors_count: Number of floors
        entrance_count: Number of entrances
        apartments_count: Number of apartments/units
        year_built: Year of construction
        notes: Free-form notes
        extra_data: Extensible JSONB field for custom attributes
        created_at: Creation timestamp
        updated_at: Last update timestamp
        created_by: User ID who created the record
        updated_by: User ID who last updated the record
        is_active: Soft delete flag
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "buildings"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    # Tenant isolation
    management_company_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Address components (required)
    city = Column(String(100), nullable=False, index=True)
    street = Column(String(200), nullable=False, index=True)
    house_number = Column(String(20), nullable=False)

    # Address components (optional)
    district = Column(String(100), nullable=True)
    building_corpus = Column(String(10), nullable=True)
    postal_code = Column(String(10), nullable=True)

    # Geocoding data
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    coordinates_source = Column(String(50), nullable=True)
    geocoded_at = Column(DateTime(timezone=True), nullable=True)

    # Building extra data
    building_type = Column(String(50), nullable=True)
    floors_count = Column(Integer, nullable=True)
    entrance_count = Column(Integer, nullable=True)
    apartments_count = Column(Integer, nullable=True)
    year_built = Column(Integer, nullable=True)

    # Additional information
    notes = Column(Text, nullable=True)
    extra_data = Column(JSONB, nullable=True, comment="Extensible JSONB for custom attributes")

    # Audit fields
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()")
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("NOW()")
    )
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Soft delete support
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs):
        """Initialize Building with defaults for created_at, updated_at, and is_active."""
        super().__init__(**kwargs)
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)
        if self.is_active is None:
            self.is_active = True

    # Table constraints
    __table_args__ = (
        # Unique address per management company (when active)
        Index(
            'ix_buildings_unique_address',
            'management_company_id', 'city', 'street', 'house_number', 'building_corpus',
            unique=True,
            postgresql_where="is_active = true AND deleted_at IS NULL",
            postgresql_nulls_not_distinct=True  # Treat NULL as equal to NULL (PostgreSQL 15+)
        ),
        # Spatial index for coordinates
        Index(
            'ix_buildings_coordinates',
            'latitude', 'longitude',
            postgresql_where="latitude IS NOT NULL AND longitude IS NOT NULL"
        ),
        # Tenant + active status
        Index('ix_buildings_mc_active', 'management_company_id', 'is_active'),
        # JSONB extra_data GIN index
        Index('ix_buildings_extra_data_gin', 'extra_data', postgresql_using='gin'),
        # City + street index (most common search)
        Index('ix_buildings_city_street', 'city', 'street'),
        # Buildings needing geocoding
        Index(
            'ix_buildings_needs_geocoding',
            'id',
            postgresql_where="latitude IS NULL AND is_active = true"
        ),
        # Validation constraints
        CheckConstraint('latitude IS NULL OR (latitude >= -90 AND latitude <= 90)', name='valid_latitude'),
        CheckConstraint('longitude IS NULL OR (longitude >= -180 AND longitude <= 180)', name='valid_longitude'),
        CheckConstraint("floors_count IS NULL OR floors_count > 0", name='positive_floors'),
        CheckConstraint("entrance_count IS NULL OR entrance_count > 0", name='positive_entrances'),
        CheckConstraint("apartments_count IS NULL OR apartments_count >= 0", name='non_negative_apartments'),
        CheckConstraint("year_built IS NULL OR (year_built >= 1800 AND year_built <= 2100)", name='reasonable_year'),
    )

    # Validators

    @validates('latitude')
    def validate_latitude(self, key: str, value: Optional[Decimal]) -> Optional[Decimal]:
        """Validate latitude is within valid range (-90 to 90)."""
        if value is not None:
            lat_float = float(value)
            if not (-90 <= lat_float <= 90):
                raise ValueError(f"Latitude must be between -90 and 90, got {lat_float}")
        return value

    @validates('longitude')
    def validate_longitude(self, key: str, value: Optional[Decimal]) -> Optional[Decimal]:
        """Validate longitude is within valid range (-180 to 180)."""
        if value is not None:
            lon_float = float(value)
            if not (-180 <= lon_float <= 180):
                raise ValueError(f"Longitude must be between -180 and 180, got {lon_float}")
        return value

    @validates('city', 'street', 'house_number')
    def validate_required_address(self, key: str, value: str) -> str:
        """Validate required address components are not empty."""
        if not value or not value.strip():
            raise ValueError(f"{key} cannot be empty")
        return value.strip()

    @validates('building_type')
    def validate_building_type(self, key: str, value: Optional[str]) -> Optional[str]:
        """Validate building type is one of allowed values."""
        if value is not None:
            allowed_types = {'residential', 'commercial', 'mixed', 'industrial', 'other'}
            if value not in allowed_types:
                raise ValueError(f"building_type must be one of {allowed_types}, got {value}")
        return value

    @validates('coordinates_source')
    def validate_coordinates_source(self, key: str, value: Optional[str]) -> Optional[str]:
        """Validate coordinates source is one of allowed values."""
        if value is not None:
            allowed_sources = {'google_maps', 'yandex_maps', 'manual', '2gis', 'osm'}
            if value not in allowed_sources:
                raise ValueError(f"coordinates_source must be one of {allowed_sources}, got {value}")
        return value

    # Hybrid properties

    @hybrid_property
    def full_address(self) -> str:
        """Generate full address string from components.

        Format: "City, [District,] Street, House Number[, Corpus Building]"

        Returns:
            str: Formatted full address
        """
        parts: List[str] = [self.city]

        if self.district:
            parts.append(self.district)

        parts.extend([self.street, self.house_number])

        if self.building_corpus:
            parts.append(f"корп. {self.building_corpus}")

        return ", ".join(parts)

    @hybrid_property
    def short_address(self) -> str:
        """Generate short address string (without city).

        Format: "Street, House Number[, Corpus Building]"

        Returns:
            str: Short address without city
        """
        parts: List[str] = [self.street, self.house_number]

        if self.building_corpus:
            parts.append(f"корп. {self.building_corpus}")

        return ", ".join(parts)

    @hybrid_property
    def has_coordinates(self) -> bool:
        """Check if building has geocoded coordinates.

        Returns:
            bool: True if both latitude and longitude are set
        """
        return self.latitude is not None and self.longitude is not None

    @hybrid_property
    def coordinates(self) -> Optional[Dict[str, float]]:
        """Get coordinates as dict.

        Returns:
            Optional[Dict[str, float]]: {'lat': float, 'lon': float} or None
        """
        if self.has_coordinates:
            return {
                'lat': float(self.latitude),
                'lon': float(self.longitude)
            }
        return None

    # Instance methods

    def set_coordinates(
        self,
        latitude: float,
        longitude: float,
        source: str = 'manual'
    ) -> None:
        """Set building coordinates with validation.

        Args:
            latitude: Latitude value (-90 to 90)
            longitude: Longitude value (-180 to 180)
            source: Source of coordinates (default: 'manual')

        Raises:
            ValueError: If coordinates are invalid
        """
        self.latitude = Decimal(str(latitude))
        self.longitude = Decimal(str(longitude))
        self.coordinates_source = source
        self.geocoded_at = datetime.now(timezone.utc)

    def soft_delete(self) -> None:
        """Soft delete the building."""
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore soft-deleted building."""
        self.is_active = True
        self.deleted_at = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert building to dictionary.

        Returns:
            Dict[str, Any]: Building data as dictionary
        """
        return {
            'id': str(self.id),
            'management_company_id': str(self.management_company_id),
            'city': self.city,
            'street': self.street,
            'house_number': self.house_number,
            'district': self.district,
            'building_corpus': self.building_corpus,
            'postal_code': self.postal_code,
            'full_address': self.full_address,
            'short_address': self.short_address,
            'coordinates': self.coordinates,
            'coordinates_source': self.coordinates_source,
            'geocoded_at': self.geocoded_at.isoformat() if self.geocoded_at else None,
            'building_type': self.building_type,
            'floors_count': self.floors_count,
            'entrance_count': self.entrance_count,
            'apartments_count': self.apartments_count,
            'year_built': self.year_built,
            'notes': self.notes,
            'extra_data': self.extra_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active if self.is_active is not None else True,
        }

    def __repr__(self) -> str:
        """String representation of Building."""
        return (
            f"<Building(id={self.id}, "
            f"address='{self.full_address}', "
            f"mc_id={self.management_company_id})>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.full_address
