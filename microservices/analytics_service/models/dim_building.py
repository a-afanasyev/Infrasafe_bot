"""
Analytics Service - Building Dimension Model
Task 10.1 - Data Warehouse Integration

Dimension table for Building Directory with SCD Type 2 (Slowly Changing Dimension)
Tracks historical changes to building data for analytics and reporting
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime, Index, text
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DimBuilding(Base):
    """
    Building Dimension Table with SCD Type 2

    SCD Type 2 tracks historical changes by creating new rows with:
    - effective_from: when this version became active
    - effective_to: when this version was superseded (NULL for current)
    - is_current: flag for active version

    Purpose:
    - Historical tracking of building changes (address updates, status changes)
    - Analytics queries can reference specific time periods
    - Enables trend analysis and audit trails

    Example:
        Building address changes:
        | building_key | building_id | address_v1 | effective_from | effective_to | is_current |
        |--------------|-------------|------------|----------------|--------------|------------|
        | 1            | uuid-123    | Old St. 1  | 2024-01-01     | 2024-06-01   | False      |
        | 2            | uuid-123    | New St. 2  | 2024-06-01     | NULL         | True       |
    """

    __tablename__ = "dim_buildings"

    # Surrogate key (auto-increment)
    building_key = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Surrogate key for dimension table"
    )

    # Natural key (from Building Directory)
    building_id = Column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Natural key - UUID from Building Directory"
    )

    # SCD Type 2 fields
    effective_from = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When this version became effective"
    )

    effective_to = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="When this version was superseded (NULL = current)"
    )

    is_current = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Flag indicating current version"
    )

    # Building attributes (denormalized from Directory)
    management_company_id = Column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Management company (tenant isolation)"
    )

    city = Column(
        String(100),
        nullable=False,
        index=True,
        comment="City name"
    )

    district = Column(
        String(100),
        nullable=True,
        comment="District/region name"
    )

    street = Column(
        String(200),
        nullable=False,
        index=True,
        comment="Street name"
    )

    house_number = Column(
        String(20),
        nullable=False,
        comment="House number"
    )

    building_corpus = Column(
        String(20),
        nullable=True,
        comment="Building corpus/section"
    )

    full_address = Column(
        String(500),
        nullable=False,
        index=True,
        comment="Full formatted address"
    )

    # Geographic coordinates
    latitude = Column(
        Numeric(10, 8),
        nullable=True,
        comment="Latitude coordinate"
    )

    longitude = Column(
        Numeric(11, 8),
        nullable=True,
        comment="Longitude coordinate"
    )

    coordinates_source = Column(
        String(50),
        nullable=True,
        comment="Source of coordinates (google_maps, manual, etc.)"
    )

    # Building metadata
    building_type = Column(
        String(50),
        nullable=True,
        comment="Building type (residential, commercial, etc.)"
    )

    floors_count = Column(
        Integer,
        nullable=True,
        comment="Number of floors"
    )

    apartments_count = Column(
        Integer,
        nullable=True,
        comment="Number of apartments/units"
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Active status in Directory"
    )

    # Audit fields
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Record update timestamp"
    )

    # Table configuration
    __table_args__ = (
        # SCD Type 2 indexes - Fast lookup of current version by natural key
        Index(
            'ix_dim_buildings_natural_key_current',
            'building_id', 'is_current',
            postgresql_where=text('is_current = true')
        ),
        # Range queries for historical lookups
        Index(
            'ix_dim_buildings_effective_range',
            'building_id', 'effective_from', 'effective_to'
        ),
        # Analytics indexes - City-based analytics queries
        Index(
            'ix_dim_buildings_city_active',
            'city', 'is_active', 'is_current'
        ),
        # Company-level analytics queries
        Index(
            'ix_dim_buildings_company_active',
            'management_company_id', 'is_active', 'is_current'
        ),
        # Spatial index (for future PostGIS integration) - Coordinate-based queries
        Index(
            'ix_dim_buildings_coordinates',
            'latitude', 'longitude',
            postgresql_where=text('latitude IS NOT NULL AND longitude IS NOT NULL')
        ),
        {
            'comment': 'Building dimension table with SCD Type 2 for historical tracking'
        }
    )

    def __repr__(self) -> str:
        return (
            f"<DimBuilding(key={self.building_key}, "
            f"id={self.building_id}, "
            f"address='{self.full_address}', "
            f"current={self.is_current})>"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            'building_key': self.building_key,
            'building_id': str(self.building_id),
            'management_company_id': str(self.management_company_id),
            'city': self.city,
            'district': self.district,
            'street': self.street,
            'house_number': self.house_number,
            'building_corpus': self.building_corpus,
            'full_address': self.full_address,
            'latitude': float(self.latitude) if self.latitude else None,
            'longitude': float(self.longitude) if self.longitude else None,
            'coordinates_source': self.coordinates_source,
            'building_type': self.building_type,
            'floors_count': self.floors_count,
            'apartments_count': self.apartments_count,
            'is_active': self.is_active,
            'effective_from': self.effective_from.isoformat() if self.effective_from else None,
            'effective_to': self.effective_to.isoformat() if self.effective_to else None,
            'is_current': self.is_current,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
