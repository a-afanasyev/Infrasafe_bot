# Models package for Shift Service
# UK Management Bot - Shift Service

from sqlalchemy.ext.declarative import declarative_base

# Create the base class for all models
Base = declarative_base()

# Import all models
from .shifts import Shift, ShiftTemplate, ShiftAssignment
from .transfers import ShiftTransfer
from .analytics import ShiftAnalytics, PerformanceMetric
from .shift_schedule import ShiftSchedule, ScheduleStatus

__all__ = [
    "Base",
    "Shift",
    "ShiftTemplate",
    "ShiftAssignment",
    "ShiftTransfer",
    "ShiftAnalytics",
    "PerformanceMetric",
    "ShiftSchedule",
    "ScheduleStatus"
]