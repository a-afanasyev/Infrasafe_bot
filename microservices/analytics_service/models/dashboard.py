"""
Dashboard Model - Dashboard Configuration

Sprint 16-18: Analytics Service
Week 7, Task 7.1: Dashboard API
Author: Analytics Team
Date: October 6, 2025

Dashboard configuration for custom analytics views.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB

from db.session import Base


class Dashboard(Base):
    """
    Dashboard configuration.

    Stores user-defined dashboard layouts and widget configurations.
    """

    __tablename__ = "dashboards"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Dashboard identification
    name = Column(String(200), nullable=False)
    """Dashboard name (e.g., "Shift Performance Overview")"""

    slug = Column(String(200), unique=True, nullable=False, index=True)
    """URL-friendly slug (e.g., "shift-performance-overview")"""

    description = Column(String(500), nullable=True)
    """Dashboard description"""

    # Ownership
    owner_id = Column(String(100), nullable=True, index=True)
    """User ID who created the dashboard (optional)"""

    is_public = Column(Boolean, default=False, nullable=False)
    """Whether dashboard is public or private"""

    is_default = Column(Boolean, default=False, nullable=False)
    """Whether this is a default system dashboard"""

    # Configuration
    layout = Column(JSONB, nullable=False)
    """
    Dashboard layout configuration:
    {
        "widgets": [
            {
                "id": "widget-1",
                "type": "kpi_card",
                "position": {"x": 0, "y": 0, "w": 4, "h": 2},
                "config": {
                    "kpi_name": "active_shifts",
                    "granularity": "daily",
                    "show_trend": true
                }
            },
            {
                "id": "widget-2",
                "type": "time_series_chart",
                "position": {"x": 4, "y": 0, "w": 8, "h": 4},
                "config": {
                    "kpis": ["active_shifts", "shift_completion_rate"],
                    "granularity": "daily",
                    "period_days": 30
                }
            }
        ],
        "grid_columns": 12,
        "row_height": 60
    }
    """

    refresh_interval = Column(Integer, default=300, nullable=False)
    """Auto-refresh interval in seconds (default: 5 minutes)"""

    # Metadata
    view_count = Column(Integer, default=0, nullable=False)
    """Number of times dashboard has been viewed"""

    last_viewed_at = Column(DateTime, nullable=True)
    """Last time dashboard was viewed"""

    # Audit fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_owner_id", "owner_id"),
        Index("idx_is_public", "is_public"),
        Index("idx_is_default", "is_default"),
    )

    def __repr__(self):
        return f"<Dashboard(name='{self.name}', slug='{self.slug}', public={self.is_public})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "owner_id": self.owner_id,
            "is_public": self.is_public,
            "is_default": self.is_default,
            "layout": self.layout,
            "refresh_interval": self.refresh_interval,
            "view_count": self.view_count,
            "last_viewed_at": self.last_viewed_at.isoformat() if self.last_viewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
