"""
Request Service - Assignment Schemas
UK Management Bot - Request Assignment Management

Extended Pydantic schemas for assignment operations including:
- Individual assignments
- Bulk assignments
- AI suggestions
- Workload analysis
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AssignmentCreate(BaseModel):
    """Schema for creating a new assignment"""
    assigned_to: int = Field(..., description="Executor user ID to assign to")
    assignment_type: Optional[str] = Field("manual", description="Assignment type (manual/auto/reassigned)")
    assignment_reason: Optional[str] = Field(None, description="Reason for assignment")

    class Config:
        json_schema_extra = {
            "example": {
                "assigned_to": 123,
                "assignment_type": "manual",
                "assignment_reason": "Best available executor for plumbing"
            }
        }


class AssignmentUpdate(BaseModel):
    """Schema for updating an assignment"""
    assignment_reason: Optional[str] = Field(None, description="Updated assignment reason")

    class Config:
        json_schema_extra = {
            "example": {
                "assignment_reason": "Updated due to executor availability"
            }
        }


class AssignmentResponse(BaseModel):
    """Response schema for assignment data"""
    id: Optional[int] = Field(None, description="Assignment record ID")
    request_number: str = Field(..., description="Request number")
    assigned_to: int = Field(..., description="Assigned executor ID")
    assigned_by: int = Field(..., description="User who made the assignment")
    assignment_type: str = Field(..., description="Assignment type")
    assignment_reason: Optional[str] = Field(None, description="Assignment reason")
    assigned_at: datetime = Field(..., description="Assignment timestamp")
    previous_assigned_to: Optional[int] = Field(None, description="Previous executor ID (for reassignments)")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "request_number": "250927-001",
                "assigned_to": 123,
                "assigned_by": 456,
                "assignment_type": "manual",
                "assignment_reason": "Executor has required plumbing specialization",
                "assigned_at": "2025-09-27T10:00:00Z",
                "previous_assigned_to": None
            }
        }


class BulkAssignmentItem(BaseModel):
    """Single item in bulk assignment request"""
    request_number: str = Field(..., description="Request number to assign")
    assigned_to: int = Field(..., description="Executor ID to assign to")

    class Config:
        json_schema_extra = {
            "example": {
                "request_number": "250927-001",
                "assigned_to": 123
            }
        }


class BulkAssignmentRequest(BaseModel):
    """Schema for bulk assignment request"""
    assignments: List[BulkAssignmentItem] = Field(..., description="List of assignments to process")
    reason: Optional[str] = Field(None, description="Common reason for all assignments")

    class Config:
        json_schema_extra = {
            "example": {
                "assignments": [
                    {"request_number": "250927-001", "assigned_to": 123},
                    {"request_number": "250927-002", "assigned_to": 124}
                ],
                "reason": "Weekly assignment optimization"
            }
        }


class BulkAssignmentResponse(BaseModel):
    """Response schema for bulk assignment operation"""
    total_requests: int = Field(..., description="Total number of requests processed")
    successful_count: int = Field(..., description="Number of successful assignments")
    failed_count: int = Field(..., description="Number of failed assignments")
    successful_assignments: List[AssignmentResponse] = Field(..., description="Successfully processed assignments")
    failed_assignments: List[Dict[str, Any]] = Field(..., description="Failed assignments with error details")

    class Config:
        json_schema_extra = {
            "example": {
                "total_requests": 2,
                "successful_count": 1,
                "failed_count": 1,
                "successful_assignments": [
                    {
                        "id": 1,
                        "request_number": "250927-001",
                        "assigned_to": 123,
                        "assigned_by": 456,
                        "assignment_type": "bulk",
                        "assignment_reason": "Weekly assignment optimization",
                        "assigned_at": "2025-09-27T10:00:00Z"
                    }
                ],
                "failed_assignments": [
                    {
                        "request_number": "250927-002",
                        "error": "Request not found"
                    }
                ]
            }
        }


class AssignmentSuggestion(BaseModel):
    """AI-powered assignment suggestion"""
    executor_id: int = Field(..., description="Suggested executor ID")
    executor_name: str = Field(..., description="Executor name")
    score: float = Field(..., ge=0.0, le=1.0, description="Suggestion confidence score (0-1)")
    reasoning: str = Field(..., description="AI reasoning for this suggestion")
    estimated_completion_time: Optional[int] = Field(None, description="Estimated completion time in minutes")
    current_workload: Optional[int] = Field(None, description="Current active requests count")

    class Config:
        json_schema_extra = {
            "example": {
                "executor_id": 123,
                "executor_name": "John Doe",
                "score": 0.95,
                "reasoning": "High expertise in plumbing, closest location, low current workload",
                "estimated_completion_time": 120,
                "current_workload": 2
            }
        }


class WorkloadAnalysis(BaseModel):
    """Executor workload analysis"""
    executor_id: int = Field(..., description="Executor ID")
    active_requests: int = Field(..., description="Number of active requests")
    completed_this_month: int = Field(..., description="Requests completed this month")
    workload_level: str = Field(..., description="Workload level (low/medium/high)")
    efficiency_score: float = Field(..., ge=0.0, le=100.0, description="Efficiency score (0-100)")
    availability_status: str = Field(..., description="Availability status (available/busy/unavailable)")

    class Config:
        json_schema_extra = {
            "example": {
                "executor_id": 123,
                "active_requests": 3,
                "completed_this_month": 15,
                "workload_level": "medium",
                "efficiency_score": 87.5,
                "availability_status": "available"
            }
        }


class AssignmentFilters(BaseModel):
    """Filters for assignment queries"""
    executor_id: Optional[int] = Field(None, description="Filter by executor ID")
    assignment_type: Optional[str] = Field(None, description="Filter by assignment type")
    date_from: Optional[datetime] = Field(None, description="Filter assignments from this date")
    date_to: Optional[datetime] = Field(None, description="Filter assignments to this date")

    class Config:
        json_schema_extra = {
            "example": {
                "executor_id": 123,
                "assignment_type": "auto",
                "date_from": "2025-09-01T00:00:00Z",
                "date_to": "2025-09-30T23:59:59Z"
            }
        }


class AssignmentStats(BaseModel):
    """Assignment statistics"""
    total_assignments: int = Field(..., description="Total number of assignments")
    manual_assignments: int = Field(..., description="Manual assignments count")
    auto_assignments: int = Field(..., description="Auto assignments count")
    reassignments: int = Field(..., description="Reassignments count")
    average_response_time: Optional[float] = Field(None, description="Average response time in hours")
    success_rate: float = Field(..., ge=0.0, le=100.0, description="Assignment success rate percentage")

    class Config:
        json_schema_extra = {
            "example": {
                "total_assignments": 150,
                "manual_assignments": 90,
                "auto_assignments": 45,
                "reassignments": 15,
                "average_response_time": 2.5,
                "success_rate": 94.5
            }
        }