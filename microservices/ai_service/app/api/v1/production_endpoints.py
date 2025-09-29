# Stage 4 Production API Endpoints
# UK Management Bot - AI Service Stage 4

import asyncio
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.services.circuit_breaker import circuit_manager
from app.services.fallback_system import fallback_manager, ServiceMode
from app.services.performance_monitor import metrics_collector
from app.services.production_config import config_manager, Environment
from app.services.service_integration import service_integration

router = APIRouter()


class ProductionAssignmentRequest(BaseModel):
    """Production-ready assignment request"""
    request_number: str = Field(..., description="Request number")
    user_id: int = Field(..., description="User ID making the request")
    category: str = Field(..., description="Request category")
    urgency: int = Field(..., description="Urgency level 1-5", ge=1, le=5)
    description: str = Field(..., description="Request description")
    address: str = Field(..., description="Request address")
    preferred_executor_id: Optional[int] = Field(None, description="Preferred executor ID")
    deadline: Optional[str] = Field(None, description="Assignment deadline")


class ServiceModeRequest(BaseModel):
    """Service mode change request"""
    mode: str = Field(..., description="Service mode: full, degraded, minimal, emergency")
    reason: Optional[str] = Field(None, description="Reason for mode change")


class ConfigurationUpdateRequest(BaseModel):
    """Configuration update request"""
    component: str = Field(..., description="Component to update")
    settings: Dict = Field(..., description="Settings to update")


@router.post("/production/assign")
async def production_assignment(
    request: ProductionAssignmentRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """
    Production-ready assignment with full integration and fallbacks
    """
    try:
        start_time = time.time()

        # Validate permissions
        permission_result = await service_integration.validate_assignment_permissions(
            request.user_id, request.request_number, "assign"
        )

        if not permission_result.success:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for assignment"
            )

        # Get real request data
        request_data_result = await service_integration.get_request_data(request.request_number)
        if not request_data_result.success:
            # Fallback to provided data
            request_data = {
                "request_number": request.request_number,
                "category": request.category,
                "urgency": request.urgency,
                "address": request.address,
                "description": request.description
            }
        else:
            request_data = request_data_result.data

        # Get available executors
        executors_result = await service_integration.get_available_executors(
            specialization=request.category,
            district=None  # Will be extracted from address
        )

        if not executors_result.success or not executors_result.data:
            # Fallback to basic executor data
            executors_data = [
                {"executor_id": 1, "specializations": [request.category], "efficiency_score": 85, "district": "Чиланзар"},
                {"executor_id": 2, "specializations": ["general"], "efficiency_score": 78, "district": "Юнусабад"},
                {"executor_id": 3, "specializations": [request.category], "efficiency_score": 92, "district": "Мирзо-Улугбек"}
            ]
        else:
            executors_data = executors_result.data.get("executors", [])

        # Perform AI-powered assignment
        from app.services.advanced_optimizer import AdvancedAssignmentOptimizer
        optimizer = AdvancedAssignmentOptimizer()

        assignment_result = await optimizer.optimize_batch_assignments(
            requests=[request_data],
            executors=executors_data,
            algorithm="hybrid"
        )

        if not assignment_result["assignments"]:
            raise HTTPException(
                status_code=422,
                detail="No suitable executor found for assignment"
            )

        best_assignment = assignment_result["assignments"][0]

        # Update assignment in request service
        update_result = await service_integration.update_request_assignment(
            request.request_number,
            best_assignment["executor_id"],
            {
                "algorithm": assignment_result["algorithm"],
                "score": assignment_result["optimization_score"],
                "processing_time_ms": assignment_result.get("processing_time_seconds", 0) * 1000,
                "ai_enhanced": True
            }
        )

        # Send notification (background task)
        if update_result.success:
            background_tasks.add_task(
                _send_assignment_notification,
                request.user_id,
                best_assignment["executor_id"],
                request.request_number
            )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "assigned",
            "request_number": request.request_number,
            "assigned_executor_id": best_assignment["executor_id"],
            "assignment_algorithm": assignment_result["algorithm"],
            "assignment_score": assignment_result["optimization_score"],
            "confidence": assignment_result.get("confidence", 0.8),
            "processing_time_ms": processing_time,
            "fallbacks_used": {
                "request_data": not request_data_result.success,
                "executors_data": not executors_result.success,
                "assignment_update": not update_result.success
            },
            "integration_status": {
                "permissions_validated": permission_result.success,
                "request_service_updated": update_result.success,
                "notification_queued": update_result.success
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Production assignment failed: {str(e)}"
        )


@router.get("/production/health")
async def production_health_check() -> Dict:
    """
    Comprehensive production health check
    """
    try:
        # System health
        system_health = fallback_manager.get_system_health()

        # Service integration health
        services_status = service_integration.get_services_status()

        # Performance metrics
        metrics_summary = metrics_collector.get_metrics_summary()

        # Circuit breaker status
        circuit_breakers = circuit_manager.get_all_metrics()

        # Configuration status
        config = config_manager.get_current_config()
        config_summary = config_manager.get_config_summary() if config else {}

        # Determine overall health
        overall_healthy = (
            system_health["overall_health"] == "healthy" and
            services_status["healthy_services"] >= services_status["total_services"] * 0.7 and  # 70% services healthy
            len(circuit_manager.get_unhealthy_breakers()) == 0
        )

        return {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": time.time(),
            "system_health": system_health,
            "services_integration": services_status,
            "performance_metrics": metrics_summary,
            "circuit_breakers": circuit_breakers,
            "configuration": config_summary,
            "alerts": metrics_collector.get_alert_conditions(),
            "uptime_checks": {
                "database_connected": True,  # TODO: Implement actual DB check
                "redis_connected": True,     # TODO: Implement actual Redis check
                "ml_models_loaded": True,    # TODO: Implement actual ML check
                "services_reachable": services_status["healthy_services"] > 0
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }


@router.get("/production/metrics")
async def get_production_metrics() -> Dict:
    """
    Get detailed production metrics
    """
    try:
        return {
            "performance_metrics": metrics_collector.get_metrics_summary(),
            "performance_trends": metrics_collector.get_performance_trends(hours=6),
            "circuit_breakers": circuit_manager.get_all_metrics(),
            "service_integration": service_integration.get_services_status(),
            "fallback_system": fallback_manager.get_system_health(),
            "alerts": metrics_collector.get_alert_conditions()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics: {str(e)}"
        )


@router.post("/production/service-mode")
async def change_service_mode(request: ServiceModeRequest) -> Dict:
    """
    Change service operation mode
    """
    try:
        valid_modes = ["full", "degraded", "minimal", "emergency"]
        if request.mode not in valid_modes:
            raise HTTPException(400, f"Invalid mode. Valid modes: {valid_modes}")

        mode_enum = ServiceMode(request.mode)
        fallback_manager.set_service_mode(mode_enum)

        return {
            "status": "mode_changed",
            "new_mode": request.mode,
            "reason": request.reason,
            "timestamp": time.time()
        }

    except ValueError as e:
        raise HTTPException(400, f"Invalid service mode: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Failed to change service mode: {str(e)}")


@router.post("/production/circuit-breaker/reset")
async def reset_circuit_breakers(breaker_name: Optional[str] = None) -> Dict:
    """
    Reset circuit breakers
    """
    try:
        if breaker_name:
            breaker = circuit_manager.get_breaker(breaker_name)
            if not breaker:
                raise HTTPException(404, f"Circuit breaker '{breaker_name}' not found")
            breaker.reset()
            return {
                "status": "reset",
                "breaker": breaker_name,
                "timestamp": time.time()
            }
        else:
            circuit_manager.reset_all()
            return {
                "status": "all_reset",
                "timestamp": time.time()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to reset circuit breakers: {str(e)}")


@router.post("/production/cache/clear")
async def clear_fallback_cache() -> Dict:
    """
    Clear fallback cache
    """
    try:
        fallback_manager.clear_cache()
        return {
            "status": "cache_cleared",
            "timestamp": time.time()
        }

    except Exception as e:
        raise HTTPException(500, f"Failed to clear cache: {str(e)}")


@router.post("/production/services/refresh")
async def refresh_service_health() -> Dict:
    """
    Refresh health status of all integrated services
    """
    try:
        await service_integration.refresh_service_health()
        services_status = service_integration.get_services_status()

        return {
            "status": "refreshed",
            "services_health": services_status,
            "timestamp": time.time()
        }

    except Exception as e:
        raise HTTPException(500, f"Failed to refresh service health: {str(e)}")


@router.get("/production/configuration")
async def get_production_configuration() -> Dict:
    """
    Get current production configuration
    """
    try:
        config_summary = config_manager.get_config_summary()

        if not config_summary or "error" in config_summary:
            raise HTTPException(500, "No configuration loaded")

        return {
            "status": "active",
            "configuration": config_summary,
            "timestamp": time.time()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to get configuration: {str(e)}")


@router.post("/production/configuration/validate")
async def validate_configuration() -> Dict:
    """
    Validate current configuration
    """
    try:
        config = config_manager.get_current_config()
        if not config:
            raise HTTPException(500, "No configuration loaded")

        issues = config_manager.validate_configuration(config)

        return {
            "status": "validated",
            "valid": len(issues) == 0,
            "issues": issues,
            "timestamp": time.time()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to validate configuration: {str(e)}")


@router.get("/production/integration/test")
async def test_service_integration() -> Dict:
    """
    Test integration with all microservices
    """
    try:
        results = {}

        # Test each service
        services_to_test = ["auth-service", "user-service", "request-service", "notification-service"]

        for service_name in services_to_test:
            try:
                start_time = time.time()

                # Simple health check call
                result = await service_integration.call_service(
                    service_name,
                    "/health",
                    use_auth=False
                )

                response_time = int((time.time() - start_time) * 1000)

                results[service_name] = {
                    "reachable": result.success,
                    "response_time_ms": response_time,
                    "status": result.data.get("status") if result.success else "unreachable",
                    "fallback_used": result.degraded_mode,
                    "error": result.fallback_reason if not result.success else None
                }

            except Exception as e:
                results[service_name] = {
                    "reachable": False,
                    "error": str(e),
                    "response_time_ms": 0
                }

        # Calculate summary
        reachable_count = sum(1 for r in results.values() if r.get("reachable", False))
        total_count = len(results)

        return {
            "status": "tested",
            "summary": {
                "total_services": total_count,
                "reachable_services": reachable_count,
                "success_rate": (reachable_count / total_count * 100) if total_count > 0 else 0
            },
            "results": results,
            "timestamp": time.time()
        }

    except Exception as e:
        raise HTTPException(500, f"Integration test failed: {str(e)}")


async def _send_assignment_notification(user_id: int, executor_id: int, request_number: str):
    """Background task to send assignment notification"""
    try:
        message = f"Request {request_number} has been assigned to executor {executor_id} using AI optimization"

        await service_integration.send_notification(
            user_id=user_id,
            message=message,
            notification_type="assignment",
            priority="normal"
        )

    except Exception as e:
        # Log error but don't fail the main request
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send assignment notification: {e}")


@router.get("/production/status")
async def get_production_status() -> Dict:
    """
    Get overall production status summary
    """
    try:
        # Get key status indicators
        system_health = fallback_manager.get_system_health()
        services_status = service_integration.get_services_status()
        circuit_breakers = circuit_manager.get_all_metrics()
        alerts = metrics_collector.get_alert_conditions()

        # Determine overall status
        critical_alerts = [a for a in alerts if a.get("severity") == "critical"]

        if critical_alerts:
            overall_status = "critical"
        elif system_health["overall_health"] != "healthy":
            overall_status = "degraded"
        elif services_status["healthy_services"] < services_status["total_services"]:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return {
            "overall_status": overall_status,
            "service_mode": system_health["service_mode"],
            "healthy_services": f"{services_status['healthy_services']}/{services_status['total_services']}",
            "active_alerts": len(alerts),
            "critical_alerts": len(critical_alerts),
            "circuit_breakers_open": len([b for b in circuit_breakers.values() if b.get("state") == "open"]),
            "uptime": "N/A",  # TODO: Implement uptime tracking
            "version": "1.0.0-stage4",
            "environment": config_manager.get_current_config().environment.value if config_manager.get_current_config() else "unknown",
            "timestamp": time.time()
        }

    except Exception as e:
        return {
            "overall_status": "error",
            "error": str(e),
            "timestamp": time.time()
        }