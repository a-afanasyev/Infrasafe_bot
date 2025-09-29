# Stage 3 Optimization API Endpoints
# UK Management Bot - AI Service Stage 3

import asyncio
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.geo_optimizer import GeoOptimizer
from app.services.advanced_optimizer import AdvancedAssignmentOptimizer

router = APIRouter()

# Initialize optimization services
geo_optimizer = GeoOptimizer()
advanced_optimizer = AdvancedAssignmentOptimizer()


class BatchOptimizationRequest(BaseModel):
    """Batch optimization request"""
    requests: List[Dict] = Field(..., description="List of requests to optimize")
    executors: List[Dict] = Field(..., description="List of available executors")
    algorithm: str = Field("hybrid", description="Optimization algorithm: genetic, simulated_annealing, hybrid")
    enable_geographic: bool = Field(True, description="Enable geographic optimization")
    enable_ml: bool = Field(True, description="Enable ML predictions")


class RouteOptimizationRequest(BaseModel):
    """Route optimization request"""
    executor_id: int = Field(..., description="Executor ID")
    assignments: List[Dict] = Field(..., description="List of assignments to optimize route for")
    transport_type: str = Field("car", description="Transport type: car, motorcycle, public")


class GeographicAnalysisRequest(BaseModel):
    """Geographic analysis request"""
    historical_requests: List[Dict] = Field(..., description="Historical request data")
    analysis_type: str = Field("positioning", description="Analysis type: positioning, clustering, coverage")


@router.post("/optimization/batch-assign")
async def batch_assignment_optimization(
    request: BatchOptimizationRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """Advanced batch assignment optimization using multiple algorithms"""
    try:
        start_time = time.time()

        if not request.requests or not request.executors:
            raise HTTPException(400, "Both requests and executors must be provided")

        # Validate algorithm
        valid_algorithms = ["genetic", "simulated_annealing", "hybrid", "greedy"]
        if request.algorithm not in valid_algorithms:
            raise HTTPException(400, f"Algorithm must be one of: {valid_algorithms}")

        # Run optimization
        result = await advanced_optimizer.optimize_batch_assignments(
            request.requests,
            request.executors,
            request.algorithm
        )

        # Add geographic analysis if enabled
        if request.enable_geographic:
            geographic_clusters = await geo_optimizer.cluster_requests_by_geography(request.requests)
            result["geographic_analysis"] = {
                "clusters": len(geographic_clusters),
                "cluster_distribution": {k: len(v) for k, v in geographic_clusters.items()}
            }

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "optimized",
            "algorithm": request.algorithm,
            "assignments": result["assignments"],
            "optimization_score": result["optimization_score"],
            "metrics": result["metrics"],
            "processing_time_ms": processing_time,
            "optimization_details": result.get("optimization_details", {}),
            "total_requests": len(request.requests),
            "assigned_requests": len(result["assignments"]),
            "success_rate": len(result["assignments"]) / len(request.requests) * 100 if request.requests else 0
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch optimization failed: {str(e)}"
        )


@router.post("/optimization/route-optimize")
async def route_optimization(
    request: RouteOptimizationRequest
) -> Dict:
    """Optimize route for executor with multiple assignments"""
    try:
        start_time = time.time()

        if not request.assignments:
            raise HTTPException(400, "Assignments list cannot be empty")

        # Run route optimization
        result = await geo_optimizer.optimize_route(
            request.executor_id,
            request.assignments
        )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "route_optimized",
            "executor_id": request.executor_id,
            "optimized_route": result["optimized_route"],
            "route_districts": result.get("route_districts", []),
            "total_distance_km": result.get("total_distance_km", 0),
            "total_travel_time_minutes": result.get("total_travel_time_minutes", 0),
            "optimization_improvement": result.get("optimization_improvement", 0),
            "algorithm": result.get("algorithm", "route_optimization"),
            "processing_time_ms": processing_time,
            "transport_type": request.transport_type
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Route optimization failed: {str(e)}"
        )


@router.post("/geographic/analyze")
async def geographic_analysis(
    request: GeographicAnalysisRequest
) -> Dict:
    """Perform geographic analysis on historical data"""
    try:
        start_time = time.time()

        if request.analysis_type == "positioning":
            result = await geo_optimizer.calculate_optimal_executor_positioning(
                request.historical_requests
            )
        elif request.analysis_type == "clustering":
            result = await geo_optimizer.cluster_requests_by_geography(
                request.historical_requests
            )
            # Convert to serializable format
            result = {
                "clusters": {k: len(v) for k, v in result.items()},
                "total_clusters": len(result),
                "cluster_details": result
            }
        else:
            raise HTTPException(400, f"Unknown analysis type: {request.analysis_type}")

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "analyzed",
            "analysis_type": request.analysis_type,
            "results": result,
            "processing_time_ms": processing_time,
            "analyzed_requests": len(request.historical_requests)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Geographic analysis failed: {str(e)}"
        )


@router.get("/geographic/distance")
async def calculate_distance(
    district1: str,
    district2: str,
    transport_type: str = "car"
) -> Dict:
    """Calculate distance and travel time between districts"""
    try:
        distance_km = geo_optimizer.get_district_distance(district1, district2)
        travel_time_minutes = geo_optimizer.calculate_travel_time(
            district1, district2, transport_type
        )

        return {
            "district1": district1,
            "district2": district2,
            "distance_km": round(distance_km, 2),
            "travel_time_minutes": travel_time_minutes,
            "transport_type": transport_type,
            "same_district": district1 == district2
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Distance calculation failed: {str(e)}"
        )


@router.get("/geographic/districts")
async def list_districts() -> Dict:
    """List all available districts with coordinates"""
    try:
        districts = {}
        for district, coords in geo_optimizer.district_coordinates.items():
            districts[district] = {
                "latitude": coords[0],
                "longitude": coords[1],
                "coordinates": coords
            }

        return {
            "districts": districts,
            "total_districts": len(districts),
            "coverage_area": "Tashkent metropolitan area"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Districts listing failed: {str(e)}"
        )


@router.post("/optimization/compare-algorithms")
async def compare_optimization_algorithms(
    request: BatchOptimizationRequest
) -> Dict:
    """Compare performance of different optimization algorithms"""
    try:
        start_time = time.time()

        if not request.requests or not request.executors:
            raise HTTPException(400, "Both requests and executors must be provided")

        algorithms = ["greedy", "genetic", "simulated_annealing", "hybrid"]
        results = {}

        for algorithm in algorithms:
            try:
                algorithm_start = time.time()

                if algorithm == "greedy":
                    # Use simple greedy from advanced optimizer
                    result = await advanced_optimizer._greedy_optimization(
                        request.requests, request.executors
                    )
                else:
                    result = await advanced_optimizer.optimize_batch_assignments(
                        request.requests, request.executors, algorithm
                    )

                algorithm_time = (time.time() - algorithm_start) * 1000

                results[algorithm] = {
                    "score": result.get("optimization_score", result.get("score", 0)),
                    "assignments": len(result.get("assignments", [])),
                    "processing_time_ms": round(algorithm_time, 2),
                    "success_rate": len(result.get("assignments", [])) / len(request.requests) * 100
                }

            except Exception as e:
                results[algorithm] = {
                    "error": str(e),
                    "score": 0,
                    "assignments": 0,
                    "processing_time_ms": 0,
                    "success_rate": 0
                }

        # Find best algorithm
        best_algorithm = max(results.keys(),
                           key=lambda x: results[x].get("score", 0) if "error" not in results[x] else -1)

        total_time = int((time.time() - start_time) * 1000)

        return {
            "status": "compared",
            "algorithms_tested": algorithms,
            "results": results,
            "best_algorithm": best_algorithm,
            "best_score": results[best_algorithm].get("score", 0),
            "total_processing_time_ms": total_time,
            "recommendation": f"Use {best_algorithm} for this type of optimization"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Algorithm comparison failed: {str(e)}"
        )


@router.get("/optimization/status")
async def get_optimization_status() -> Dict:
    """Get status of optimization services"""
    try:
        geo_health = await geo_optimizer.health_check()
        advanced_health = await advanced_optimizer.health_check()

        return {
            "optimization_enabled": True,
            "services": {
                "geographic_optimizer": {
                    "status": geo_health,
                    "healthy": geo_health == "healthy",
                    "districts_supported": len(geo_optimizer.district_coordinates),
                    "features": ["distance_calculation", "route_optimization", "geographic_clustering"]
                },
                "advanced_optimizer": {
                    "status": advanced_health,
                    "healthy": advanced_health == "healthy",
                    "algorithms": ["genetic", "simulated_annealing", "hybrid", "greedy"],
                    "features": ["batch_optimization", "multi_objective", "ml_integration"]
                }
            },
            "capabilities": {
                "geographic_optimization": True,
                "route_optimization": True,
                "batch_assignment": True,
                "algorithm_comparison": True,
                "ml_integration": True
            }
        }

    except Exception as e:
        return {
            "optimization_enabled": False,
            "error": str(e),
            "services": {
                "geographic_optimizer": {"status": f"error: {str(e)}", "healthy": False},
                "advanced_optimizer": {"status": f"error: {str(e)}", "healthy": False}
            }
        }


@router.get("/optimization/config")
async def get_optimization_config() -> Dict:
    """Get optimization algorithm configurations"""
    return {
        "genetic_algorithm": advanced_optimizer.ga_config,
        "simulated_annealing": advanced_optimizer.sa_config,
        "weights": advanced_optimizer.weights,
        "geographic_config": {
            "max_distance_km": geo_optimizer.max_distance_km,
            "max_assignments_per_executor": geo_optimizer.max_assignments_per_executor,
            "distance_weight": geo_optimizer.distance_weight,
            "travel_speeds": geo_optimizer.travel_speeds
        }
    }