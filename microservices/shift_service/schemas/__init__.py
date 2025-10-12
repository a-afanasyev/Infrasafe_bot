# Schemas package for Shift Service
# UK Management Bot - Shift Service

from .shifts import *
from .transfers import *
from .analytics import *
from .common import *

__all__ = [
    # Common schemas
    "PaginationParams",
    "PaginatedResponse",
    "ErrorResponse",

    # Shift schemas
    "ShiftCreate",
    "ShiftUpdate",
    "ShiftResponse",
    "ShiftListResponse",
    "ShiftTemplateCreate",
    "ShiftTemplateResponse",
    "ShiftAssignmentCreate",
    "ShiftAssignmentResponse",

    # Transfer schemas
    "ShiftTransferCreate",
    "ShiftTransferUpdate",
    "ShiftTransferResponse",
    "TransferApprovalRequest",

    # Analytics schemas
    "AnalyticsQuery",
    "AnalyticsResponse",
    "PerformanceMetricResponse",
    "ShiftStatistics"
]