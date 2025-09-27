"""
Request Service - Schemas Module
UK Management Bot - Request Management System

Pydantic schemas for API request/response validation.
"""

from .request import (
    # Request schemas
    RequestBase,
    RequestCreate,
    RequestUpdate,
    RequestStatusUpdate,
    RequestResponse,
    RequestSummaryResponse,
    RequestListResponse,

    # Comment schemas
    CommentBase,
    CommentCreate,
    CommentUpdate,
    CommentResponse,

    # Rating schemas
    RatingBase,
    RatingCreate,
    RatingUpdate,
    RatingResponse,

    # Material schemas
    MaterialBase,
    MaterialCreate,
    MaterialUpdate,
    MaterialResponse,

    # Search and filter schemas
    RequestFilters,
    RequestSearchQuery,
    RequestStatsResponse,

    # Error schemas
    ErrorResponse,
)

from .assignment import (
    # Assignment schemas
    AssignmentCreate,
    AssignmentUpdate,
    AssignmentResponse,
    BulkAssignmentItem,
    BulkAssignmentRequest,
    BulkAssignmentResponse,
    AssignmentSuggestion,
    WorkloadAnalysis,
    AssignmentFilters,
    AssignmentStats,
)

from .material import (
    # Material schemas
    MaterialBase,
    MaterialCreate,
    MaterialUpdate,
    MaterialResponse,
    BulkMaterialRequest,
    BulkMaterialResponse,
    MaterialCostSummary,
    MaterialStats,
    MaterialFilters,
)

__all__ = [
    # Request schemas
    "RequestBase",
    "RequestCreate",
    "RequestUpdate",
    "RequestStatusUpdate",
    "RequestResponse",
    "RequestSummaryResponse",
    "RequestListResponse",

    # Comment schemas
    "CommentBase",
    "CommentCreate",
    "CommentUpdate",
    "CommentResponse",

    # Rating schemas
    "RatingBase",
    "RatingCreate",
    "RatingUpdate",
    "RatingResponse",

    # Assignment schemas (from assignment.py)
    "AssignmentCreate",
    "AssignmentUpdate",
    "AssignmentResponse",
    "BulkAssignmentItem",
    "BulkAssignmentRequest",
    "BulkAssignmentResponse",
    "AssignmentSuggestion",
    "WorkloadAnalysis",
    "AssignmentFilters",
    "AssignmentStats",

    # Material schemas (from material.py)
    "MaterialBase",
    "MaterialCreate",
    "MaterialUpdate",
    "MaterialResponse",
    "BulkMaterialRequest",
    "BulkMaterialResponse",
    "MaterialCostSummary",
    "MaterialStats",
    "MaterialFilters",

    # Material schemas (from request.py - legacy - kept for compatibility)

    # Search and filter schemas
    "RequestFilters",
    "RequestSearchQuery",
    "RequestStatsResponse",

    # Error schemas
    "ErrorResponse",
]