# AI Service - Stage 4 Production Integration + Fallbacks
# UK Management Bot - Microservices

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from config import settings
from app.api.v1 import ml_endpoints, optimization_endpoints, production_endpoints

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple models for Stage 1
class AssignmentRequest(BaseModel):
    request_number: str = Field(..., description="Request number (YYMMDD-NNN)")
    category: Optional[str] = Field(None, description="Request category")
    urgency: int = Field(1, description="Urgency level 1-5", ge=1, le=5)
    description: Optional[str] = Field(None, description="Request description")
    address: Optional[str] = Field(None, description="Request address")

class AssignmentResult(BaseModel):
    request_number: str
    success: bool
    executor_id: Optional[int] = None
    algorithm: str
    score: float
    factors: Dict[str, Any] = Field(default_factory=dict)
    processing_time_ms: int
    fallback_used: bool = False

class ExecutorRecommendation(BaseModel):
    executor_id: int
    score: float
    factors: Dict[str, Any]
    reasoning: str

# Simple Smart Dispatcher for Stage 1
class SimpleSmartDispatcher:
    def __init__(self):
        self.algorithm = "basic_rules"

        # Mock executors data
        self.executors = [
            {
                "executor_id": 1,
                "name": "Иван Иванов",
                "specializations": ["plumber"],
                "efficiency_score": 85.0,
                "current_assignments": 2,
                "district": "Чиланзар",
                "is_available": True,
                "workload_capacity": 5
            },
            {
                "executor_id": 2,
                "name": "Петр Петров",
                "specializations": ["electrician"],
                "efficiency_score": 78.0,
                "current_assignments": 1,
                "district": "Юнусабад",
                "is_available": True,
                "workload_capacity": 6
            },
            {
                "executor_id": 3,
                "name": "Сергей Сергеев",
                "specializations": ["general", "carpenter"],
                "efficiency_score": 92.0,
                "current_assignments": 0,
                "district": "Мирзо-Улугбек",
                "is_available": True,
                "workload_capacity": 4
            },
        ]

    async def assign_basic(self, request: AssignmentRequest) -> AssignmentResult:
        """Basic assignment using simple rules"""
        start_time = time.time()

        try:
            # Get available executors
            available = [e for e in self.executors if e["is_available"]]

            if not available:
                return AssignmentResult(
                    request_number=request.request_number,
                    success=False,
                    algorithm=self.algorithm,
                    score=0.0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    factors={"error": "no_available_executors"}
                )

            # Calculate scores
            scored_executors = []
            for executor in available:
                score = self._calculate_score(request, executor)
                factors = self._get_factors(request, executor)

                scored_executors.append({
                    "executor": executor,
                    "score": score,
                    "factors": factors
                })

            # Sort by score
            scored_executors.sort(key=lambda x: x["score"], reverse=True)

            if not scored_executors or scored_executors[0]["score"] < 0.3:
                return AssignmentResult(
                    request_number=request.request_number,
                    success=False,
                    algorithm=self.algorithm,
                    score=scored_executors[0]["score"] if scored_executors else 0.0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    factors={"error": "score_below_threshold"}
                )

            best = scored_executors[0]
            processing_time = int((time.time() - start_time) * 1000)

            return AssignmentResult(
                request_number=request.request_number,
                success=True,
                executor_id=best["executor"]["executor_id"],
                algorithm=self.algorithm,
                score=best["score"],
                factors=best["factors"],
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Assignment failed: {e}")
            return AssignmentResult(
                request_number=request.request_number,
                success=False,
                algorithm=self.algorithm,
                score=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                factors={"error": str(e)}
            )

    def _calculate_score(self, request: AssignmentRequest, executor: Dict) -> float:
        """Calculate assignment score"""
        # Specialization match (40%)
        spec_score = 0.5
        if request.category and request.category in executor.get("specializations", []):
            spec_score = 1.0
        elif "general" in executor.get("specializations", []):
            spec_score = 0.7

        # Efficiency (30%)
        eff_score = executor.get("efficiency_score", 50.0) / 100.0

        # Workload (20%)
        current_load = executor.get("current_assignments", 0)
        capacity = executor.get("workload_capacity", 5)
        workload_score = max(0.1, 1.0 - (current_load / capacity))

        # Availability (10%)
        avail_score = 1.0 if executor.get("is_available", False) else 0.0

        # Weighted total
        total_score = (
            spec_score * 0.4 +
            eff_score * 0.3 +
            workload_score * 0.2 +
            avail_score * 0.1
        )

        return min(max(total_score, 0.0), 1.0)

    def _get_factors(self, request: AssignmentRequest, executor: Dict) -> Dict[str, Any]:
        """Get detailed assignment factors"""
        return {
            "specialization_match": request.category in executor.get("specializations", []),
            "efficiency_score": executor.get("efficiency_score", 50.0),
            "current_load": executor.get("current_assignments", 0),
            "capacity": executor.get("workload_capacity", 5),
            "district": executor.get("district", "Unknown"),
            "executor_name": executor.get("name", f"Executor {executor['executor_id']}")
        }

    async def get_recommendations(self, request_number: str, limit: int = 5) -> List[ExecutorRecommendation]:
        """Get executor recommendations"""
        # Mock request for Stage 1
        mock_request = AssignmentRequest(
            request_number=request_number,
            category="general",
            urgency=3
        )

        recommendations = []
        for executor in self.executors[:limit]:
            score = self._calculate_score(mock_request, executor)
            factors = self._get_factors(mock_request, executor)

            reasoning = "Базовое соответствие критериям"
            if factors["specialization_match"]:
                reasoning = "Точное соответствие специализации"
            elif factors["efficiency_score"] > 80:
                reasoning = "Высокая эффективность"

            recommendations.append(ExecutorRecommendation(
                executor_id=executor["executor_id"],
                score=score,
                factors=factors,
                reasoning=reasoning
            ))

        return sorted(recommendations, key=lambda x: x.score, reverse=True)

# Initialize dispatcher
dispatcher = SimpleSmartDispatcher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    logger.info(f"Starting {settings.service_name} Stage 4")

    # Initialize Stage 4 components
    try:
        # Initialize service integration
        from app.services.service_integration import service_integration
        await service_integration.initialize()

        # Start performance monitoring
        from app.services.performance_monitor import metrics_collector
        metrics_collector.start_system_monitoring()

        # Load production configuration
        from app.services.production_config import config_manager, Environment
        config_manager.load_configuration(Environment.DEVELOPMENT)

        logger.info("Stage 4 production components initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize Stage 4 components: {e}")

    yield

    # Cleanup Stage 4 components
    try:
        await service_integration.shutdown()
        metrics_collector.stop_system_monitoring()
        logger.info("Stage 4 components shutdown completed")
    except Exception as e:
        logger.error(f"Error during Stage 4 shutdown: {e}")

    logger.info(f"Shutting down {settings.service_name}")

# Create FastAPI app
app = FastAPI(
    title="AI Service - Stage 4",
    description="Production-Ready Smart Assignment & Optimization with Fallbacks",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include ML API routes
app.include_router(ml_endpoints.router, prefix="/api/v1", tags=["ml"])

# Include Optimization API routes
app.include_router(optimization_endpoints.router, prefix="/api/v1", tags=["optimization"])

# Include Production API routes
app.include_router(production_endpoints.router, prefix="/api/v1", tags=["production"])

# Health check endpoints
@app.get("/api/v1/health")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": "1.0.0",
        "stage": "1_basic_mvp",
        "ml_enabled": settings.ml_enabled,
        "geo_enabled": settings.geo_enabled,
        "features": {
            "basic_rules": True,
            "ml_prediction": False,
            "ml_training": False,
            "data_generation": True,
            "geo_optimization": False,
            "route_optimization": False,
            "batch_assignment": True,
            "advanced_algorithms": False,
            "circuit_breaker": False,     # Stage 1 - cosmetic only
            "fallback_system": False,     # Stage 1 - cosmetic only
            "performance_monitoring": False, # Stage 1 - cosmetic only
            "service_integration": False, # Stage 1 - cosmetic only
            "production_ready": False
        }
    }

@app.get("/ready")
async def ready_check():
    """Readiness check"""
    return {"status": "ready", "service": settings.service_name}

# Assignment endpoints
@app.post("/api/v1/assignments/basic-assign", response_model=AssignmentResult)
async def basic_assignment(request: AssignmentRequest) -> AssignmentResult:
    """Stage 1: Basic assignment using SmartDispatcher rules"""
    logger.info(f"Processing assignment for {request.request_number}")
    result = await dispatcher.assign_basic(request)
    logger.info(f"Assignment result: {result.success}, executor: {result.executor_id}, score: {result.score:.3f}")
    return result

@app.get("/api/v1/assignments/recommendations/{request_number}", response_model=List[ExecutorRecommendation])
async def get_recommendations(request_number: str, limit: int = 5) -> List[ExecutorRecommendation]:
    """Get executor recommendations"""
    logger.info(f"Getting recommendations for {request_number}")
    recommendations = await dispatcher.get_recommendations(request_number, limit)
    return recommendations

@app.get("/api/v1/assignments/stats")
async def get_stats():
    """Get assignment statistics"""
    return {
        "stage": "1_basic_mvp",
        "ml_enabled": False,
        "geo_enabled": False,
        "total_assignments": 0,  # Will be tracked in Stage 2+
        "success_rate": 0.0,
        "algorithms": {
            "basic_rules": 0
        },
        "features_available": ["basic_assignment", "executor_recommendations"]
    }

# Test endpoint
@app.get("/api/v1/test")
async def test_endpoint():
    """Test endpoint for Stage 4"""
    return {
        "message": "AI Service Stage 4 Production Integration + Fallbacks is working!",
        "stage": "1_basic_mvp",
        "timestamp": time.time(),
        "available_endpoints": [
            "/api/v1/assignments/basic-assign",
            "/api/v1/assignments/ml-assign",
            "/api/v1/production/assign",
            "/api/v1/optimization/batch-assign",
            "/api/v1/optimization/route-optimize",
            "/api/v1/geographic/distance",
            "/api/v1/ml/initialize",
            "/api/v1/ml/predict",
            "/api/v1/production/health",
            "/api/v1/production/metrics",
            "/api/v1/production/service-mode",
            "/api/v1/production/status",
            "/api/v1/health"
        ]
    }

if __name__ == "__main__":
    uvicorn.run(
        "main_simple:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )