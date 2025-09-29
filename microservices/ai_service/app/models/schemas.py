# AI Service Data Models and Schemas
# UK Management Bot - Stage 1

from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class AssignmentAlgorithm(str, Enum):
    """Available assignment algorithms"""
    BASIC_RULES = "basic_rules"
    SMART_DISPATCH = "smart_dispatch"
    ML_PREDICTION = "ml_prediction"
    GEO_OPTIMIZED = "geo_optimized"
    HYBRID = "hybrid"


class RequestStatus(str, Enum):
    """Request status options"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssignmentRequest(BaseModel):
    """Assignment request model"""
    request_number: str = Field(..., description="Unique request identifier")
    category: Optional[str] = Field(None, description="Request category/specialization")
    urgency: int = Field(1, description="Urgency level 1-5", ge=1, le=5)
    description: Optional[str] = Field(None, description="Request description")
    address: Optional[str] = Field(None, description="Request address")
    created_by: Optional[int] = Field(None, description="User ID who created request")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ExecutorInfo(BaseModel):
    """Executor information for assignment"""
    executor_id: int
    name: Optional[str] = None
    specializations: List[str] = Field(default_factory=list)
    efficiency_score: Optional[float] = None
    quality_rating: Optional[float] = None
    current_assignments: int = 0
    average_completion_time: Optional[float] = None
    district: Optional[str] = None
    is_available: bool = True
    workload_capacity: int = 10


class AssignmentResult(BaseModel):
    """Assignment result model"""
    success: bool
    executor_id: Optional[int] = None
    score: float = 0.0
    algorithm: AssignmentAlgorithm
    factors: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    alternative_executors: List[int] = Field(default_factory=list)
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None


class RecommendationItem(BaseModel):
    """Single executor recommendation"""
    executor_id: int
    score: float
    rank: int
    factors: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class RecommendationResponse(BaseModel):
    """Response model for executor recommendations"""
    request_number: str
    recommendations: List[RecommendationItem]
    algorithm: AssignmentAlgorithm
    total_evaluated: int
    generated_at: datetime = Field(default_factory=datetime.now)


class AssignmentStats(BaseModel):
    """Assignment statistics model"""
    total_assignments: int = 0
    successful_assignments: int = 0
    failed_assignments: int = 0
    success_rate: float = 0.0
    average_score: float = 0.0
    average_processing_time_ms: float = 0.0
    algorithms_used: Dict[str, int] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.now)


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str = "healthy"
    service: str = "ai-service"
    version: str = "1.0.0"
    stage: str = "1_basic_assignment"
    timestamp: datetime = Field(default_factory=datetime.now)
    components: Dict[str, str] = Field(default_factory=dict)
    features: Dict[str, bool] = Field(default_factory=dict)


class AssignmentHistory(BaseModel):
    """Assignment history record"""
    id: int
    request_number: str
    executor_id: Optional[int]
    algorithm: str
    score: float
    factors: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    created_at: datetime


class DistrictMapping(BaseModel):
    """District mapping for geographic optimization"""
    id: int
    address_pattern: str
    district: str
    region: str
    proximity_group: int


class MLModelInfo(BaseModel):
    """ML Model information (for Stage 2+)"""
    id: str
    name: str
    version: str
    model_type: str
    is_active: bool
    training_config: Dict[str, Any]
    validation_accuracy: Optional[float] = None
    trained_at: datetime
    activated_at: Optional[datetime] = None


class AssignmentFactors(BaseModel):
    """Detailed assignment factors for analysis"""
    specialization_match: bool = False
    specialization_score: float = 0.0
    efficiency_score: float = 0.0
    workload_score: float = 0.0
    geographic_score: float = 0.0
    urgency_factor: float = 1.0
    availability_score: float = 0.0
    quality_factor: float = 0.0
    time_preference_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssignmentFactors":
        """Create from dictionary"""
        return cls(**data)