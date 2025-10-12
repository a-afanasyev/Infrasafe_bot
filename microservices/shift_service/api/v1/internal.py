# Internal API Router for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.common import ServiceHealth, ServiceInfo
from services.scheduler_service import get_scheduler_status, trigger_job_manually
from services.ai_integration import AIIntegrationService
from utils.migration_utils import DataMigrationService
from middleware.auth_middleware import get_current_user

router = APIRouter()


@router.get("/health", response_model=ServiceHealth)
async def internal_health_check(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Internal health check with detailed status

    Requires: internal:health permission
    """
    from database import check_database_connection

    try:
        # Check database
        db_health = await check_database_connection()

        # Check scheduler
        scheduler_status = await get_scheduler_status()

        health_data = {
            "status": "healthy" if db_health["status"] == "healthy" else "unhealthy",
            "service": "shift-service",
            "version": "1.0.0",
            "timestamp": datetime.utcnow(),
            "database": db_health,
            "dependencies": {
                "scheduler": scheduler_status,
                "background_tasks": scheduler_status.get("job_count", 0)
            }
        }

        return health_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {e}"
        )


@router.get("/info", response_model=ServiceInfo)
async def service_info(current_user: dict = Depends(get_current_user)):
    """
    Get detailed service information

    Requires: internal:info permission
    """
    from config import settings

    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "description": "UK Management Bot - Shift Planning & Management Service",
        "port": settings.port,
        "environment": settings.environment
    }


@router.get("/scheduler/status")
async def get_internal_scheduler_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get detailed scheduler status

    Requires: internal:scheduler permission
    """
    try:
        status = await get_scheduler_status()
        return status
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduler status: {e}"
        )


@router.post("/scheduler/trigger/{job_id}")
async def trigger_background_job(
    job_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Manually trigger a background job

    Requires: internal:scheduler permission
    """
    try:
        success = await trigger_job_manually(job_id)

        if success:
            return {"status": "triggered", "job_id": job_id}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found or scheduler not running"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger job: {e}"
        )


@router.get("/migration/status")
async def get_migration_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get migration status and statistics

    Requires: internal:migration permission
    """
    try:
        from sqlalchemy import text

        # Get basic statistics
        result = await db.execute(text("SELECT COUNT(*) FROM shifts"))
        shift_count = result.scalar()

        result = await db.execute(text("SELECT COUNT(*) FROM shift_templates"))
        template_count = result.scalar()

        result = await db.execute(text("SELECT COUNT(*) FROM shift_assignments"))
        assignment_count = result.scalar()

        result = await db.execute(text("SELECT COUNT(*) FROM shift_transfers"))
        transfer_count = result.scalar()

        # Get recent activity
        result = await db.execute(text("""
            SELECT COUNT(*) FROM shifts
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """))
        recent_shifts = result.scalar()

        return {
            "statistics": {
                "shifts": shift_count,
                "templates": template_count,
                "assignments": assignment_count,
                "transfers": transfer_count
            },
            "recent_activity": {
                "shifts_24h": recent_shifts
            },
            "migration_ready": True,
            "last_check": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get migration status: {e}"
        )


@router.post("/migration/validate")
async def validate_migration_data(
    source_connection: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate migration data from source

    Requires: internal:migration permission
    """
    try:
        service = DataMigrationService()
        report = await service.migrate_shifts_from_monolith(
            source_connection, validation_mode=True
        )
        return report

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration validation failed: {e}"
        )


@router.get("/metrics")
async def get_service_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get service metrics for monitoring

    Requires: internal:metrics permission
    """
    try:
        from sqlalchemy import text

        # Performance metrics
        result = await db.execute(text("""
            SELECT
                COUNT(*) as total_shifts,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_shifts,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_shifts,
                COUNT(CASE WHEN status = 'planned' THEN 1 END) as planned_shifts,
                COUNT(CASE WHEN executor_id IS NULL THEN 1 END) as unassigned_shifts,
                AVG(CASE WHEN completion_rating IS NOT NULL THEN completion_rating END) as avg_rating,
                AVG(CASE WHEN efficiency_score IS NOT NULL THEN efficiency_score END) as avg_efficiency
            FROM shifts
            WHERE start_time >= NOW() - INTERVAL '7 days'
        """))

        metrics_row = result.fetchone()

        # Scheduler metrics
        scheduler_status = await get_scheduler_status()

        return {
            "service_metrics": {
                "total_shifts_7d": metrics_row[0] or 0,
                "completed_shifts_7d": metrics_row[1] or 0,
                "active_shifts": metrics_row[2] or 0,
                "planned_shifts": metrics_row[3] or 0,
                "unassigned_shifts": metrics_row[4] or 0,
                "average_rating": float(metrics_row[5]) if metrics_row[5] else 0,
                "average_efficiency": float(metrics_row[6]) if metrics_row[6] else 0
            },
            "scheduler_metrics": {
                "status": scheduler_status.get("status"),
                "active_jobs": scheduler_status.get("job_count", 0)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics: {e}"
        )


@router.get("/shifts/summary")
async def get_shifts_summary(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get shifts summary for integration with other services

    Requires: internal:shifts permission
    """
    try:
        from sqlalchemy import text

        # Get shifts summary by status
        result = await db.execute(text("""
            SELECT
                status,
                COUNT(*) as count,
                COUNT(CASE WHEN executor_id IS NOT NULL THEN 1 END) as assigned_count
            FROM shifts
            WHERE start_time >= NOW() - INTERVAL '1 day'
            AND start_time <= NOW() + INTERVAL '7 days'
            GROUP BY status
        """))

        status_summary = {}
        for row in result:
            status_summary[row[0]] = {
                "total": row[1],
                "assigned": row[2],
                "unassigned": row[1] - row[2]
            }

        # Get urgent shifts
        result = await db.execute(text("""
            SELECT COUNT(*) FROM shifts
            WHERE priority >= 3
            AND status = 'planned'
            AND start_time <= NOW() + INTERVAL '24 hours'
        """))
        urgent_shifts = result.scalar()

        return {
            "summary": {
                "by_status": status_summary,
                "urgent_shifts_24h": urgent_shifts
            },
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get shifts summary: {e}"
        )


# AI Service Integration Management Endpoints

@router.get("/ai/health")
async def get_ai_service_health(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Check AI service health and get fallback status

    Requires: internal:ai permission
    """
    try:
        ai_service = AIIntegrationService()
        health_status = await ai_service.check_ai_service_health()
        fallback_status = await ai_service.get_fallback_status()

        return {
            "ai_service_health": health_status,
            "fallback_status": fallback_status,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check AI service health: {e}"
        )


@router.get("/ai/fallback/status")
async def get_ai_fallback_status(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get detailed AI fallback configuration and status

    Requires: internal:ai permission
    """
    try:
        from config import settings

        ai_service = AIIntegrationService()
        status = await ai_service.get_fallback_status()

        return {
            "configuration": {
                "fallback_enabled": settings.ai_fallback_enabled,
                "fallback_mode": settings.ai_fallback_mode,
                "fallback_confidence": settings.ai_fallback_confidence,
                "mock_data_enabled": settings.ai_mock_data_enabled,
                "ai_service_url": settings.ai_service_url,
                "timeout": settings.ai_prediction_timeout
            },
            "current_status": status,
            "available_modes": ["simple", "enhanced", "historical"],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get fallback status: {e}"
        )


@router.post("/ai/fallback/test")
async def test_ai_fallback_modes(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Test all AI fallback modes with sample data

    Requires: internal:ai permission
    """
    try:
        ai_service = AIIntegrationService()

        # Sample test data
        test_shift_data = {
            "shift_id": "test-shift-001",
            "specialization": "plumbing",
            "location": {"lat": 55.7558, "lon": 37.6176},
            "urgency": "high",
            "start_time": datetime.utcnow().isoformat()
        }

        test_optimization_data = {
            "shifts": [test_shift_data],
            "executors": [
                {"id": "exec_001", "specialization": "plumbing", "location": {"lat": 55.7500, "lon": 37.6000}},
                {"id": "exec_002", "specialization": "electrical", "location": {"lat": 55.7600, "lon": 37.6200}}
            ]
        }

        test_prediction_data = {
            "target_date": datetime.utcnow().date().isoformat(),
            "historical_days": 30
        }

        # Test different fallback modes
        results = {}

        # Test optimization fallback
        optimization_result = await ai_service._fallback_optimization(test_optimization_data)
        results["optimization_fallback"] = optimization_result

        # Test workload prediction fallback
        prediction_result = await ai_service._fallback_workload_prediction(test_prediction_data)
        results["workload_prediction_fallback"] = prediction_result

        # Test assignment recommendations fallback
        assignment_result = await ai_service._fallback_assignment_recommendations(test_shift_data)
        results["assignment_recommendations_fallback"] = assignment_result

        return {
            "test_results": results,
            "test_data": {
                "shift_data": test_shift_data,
                "optimization_data": test_optimization_data,
                "prediction_data": test_prediction_data
            },
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test fallback modes: {e}"
        )


@router.post("/ai/test/integration")
async def test_ai_integration(
    test_mode: str = "all",  # all, optimization, prediction, assignment
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Test AI service integration with real or fallback responses

    Requires: internal:ai permission
    """
    try:
        ai_service = AIIntegrationService()
        results = {}

        # Test data
        test_shift = {
            "id": "test-integration-001",
            "specialization": "maintenance",
            "location": {"lat": 55.7558, "lon": 37.6176},
            "urgency": "medium"
        }

        test_optimization = {
            "shifts": [test_shift],
            "executors": [
                {"id": "test_exec_001", "specialization": "maintenance"},
                {"id": "test_exec_002", "specialization": "cleaning"}
            ]
        }

        test_prediction = {
            "target_date": datetime.utcnow().date().isoformat(),
            "specialization": "maintenance"
        }

        if test_mode in ["all", "optimization"]:
            optimization_result = await ai_service.optimize_shift_assignments(test_optimization)
            results["optimization"] = {
                "success": optimization_result is not None,
                "result": optimization_result,
                "is_fallback": optimization_result.get("fallback", False) if optimization_result else None
            }

        if test_mode in ["all", "prediction"]:
            prediction_result = await ai_service.predict_workload(test_prediction)
            results["workload_prediction"] = {
                "success": prediction_result is not None,
                "result": prediction_result,
                "is_fallback": prediction_result.get("fallback", False) if prediction_result else None
            }

        if test_mode in ["all", "assignment"]:
            assignment_result = await ai_service.get_assignment_recommendations(test_shift)
            results["assignment_recommendations"] = {
                "success": assignment_result is not None,
                "result": assignment_result,
                "count": len(assignment_result) if assignment_result else 0
            }

        # Overall integration health
        ai_health = await ai_service.check_ai_service_health()

        return {
            "integration_test_results": results,
            "ai_service_health": ai_health,
            "test_mode": test_mode,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI integration test failed: {e}"
        )