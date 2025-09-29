# ML API Endpoints
# UK Management Bot - AI Service Stage 2

import asyncio
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.ml_pipeline import MLPipelineService
from app.services.data_generator import DataGeneratorService
from app.models.schemas import AssignmentRequest, AssignmentResult

router = APIRouter()

# Initialize ML services
ml_pipeline = MLPipelineService()
data_generator = DataGeneratorService()


class MLTrainingRequest(BaseModel):
    """ML model training request"""
    use_synthetic_data: bool = Field(True, description="Use synthetic data for training")
    sample_count: int = Field(500, description="Number of training samples", ge=100, le=2000)
    model_type: str = Field("success_prediction", description="Type of model to train")


class MLPredictionRequest(BaseModel):
    """ML prediction request"""
    request_number: str = Field(..., description="Request number")
    executor_id: int = Field(..., description="Executor ID")
    category: str = Field(..., description="Request category")
    urgency: int = Field(3, description="Urgency level", ge=1, le=5)
    district: str = Field(..., description="Request district")
    executor_district: str = Field(..., description="Executor district")
    efficiency_score: float = Field(75.0, description="Executor efficiency score")
    current_workload: int = Field(3, description="Current workload")


class MLModelInfo(BaseModel):
    """ML model information"""
    id: str
    name: str
    version: str
    model_type: str
    accuracy: float
    is_active: bool
    trained_at: str
    training_samples: int


class DataGenerationRequest(BaseModel):
    """Data generation request"""
    count: int = Field(500, description="Number of assignments to generate", ge=50, le=2000)
    export_format: str = Field("ml_ready", description="Export format")


@router.post("/ml/initialize")
async def initialize_ml_pipeline(
    request: MLTrainingRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """Initialize ML pipeline with training data"""
    try:
        start_time = time.time()

        # Initialize pipeline
        result = await ml_pipeline.initialize_ml_pipeline(
            use_synthetic_data=request.use_synthetic_data
        )

        # Auto-activate the trained model
        if result.get("model_id"):
            await ml_pipeline.activate_model(result["model_id"])

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "status": "initialized",
            "ml_pipeline": result,
            "processing_time_ms": processing_time,
            "message": "ML pipeline initialized and model activated"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML pipeline initialization failed: {str(e)}"
        )


@router.post("/ml/train")
async def train_new_model(
    request: MLTrainingRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """Train a new ML model"""
    try:
        start_time = time.time()

        # Generate training data
        if request.use_synthetic_data:
            assignments = await data_generator.generate_historical_assignments(
                count=request.sample_count
            )
            dataset = await data_generator.export_training_dataset(assignments)
        else:
            # TODO: Load real data
            raise HTTPException(400, "Real data training not yet implemented")

        # Train model
        model_id = await ml_pipeline.train_model(dataset, request.model_type)

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "model_id": model_id,
            "training_samples": dataset["sample_count"],
            "processing_time_ms": processing_time,
            "status": "trained",
            "message": f"Model {model_id} trained successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Model training failed: {str(e)}"
        )


@router.post("/ml/activate/{model_id}")
async def activate_model(model_id: str) -> Dict:
    """Activate ML model for production use"""
    try:
        success = await ml_pipeline.activate_model(model_id)

        if not success:
            raise HTTPException(404, f"Failed to activate model {model_id}")

        return {
            "model_id": model_id,
            "status": "activated",
            "message": f"Model {model_id} is now active"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Model activation failed: {str(e)}"
        )


@router.post("/ml/predict", response_model=Dict)
async def ml_predict_assignment_success(
    request: MLPredictionRequest
) -> Dict:
    """Predict assignment success using ML"""
    try:
        start_time = time.time()

        # Extract features for ML
        features = {
            "specialization_match": True,  # TODO: Calculate based on request.category
            "efficiency_score": request.efficiency_score,
            "urgency": request.urgency,
            "district_match": request.district == request.executor_district,
            "workload": request.current_workload,
            "hour_of_day": 14,  # TODO: Use actual time
            "day_of_week": 2    # TODO: Use actual day
        }

        # Get ML prediction
        prediction = await ml_pipeline.predict_assignment_success(features)

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "request_number": request.request_number,
            "executor_id": request.executor_id,
            "prediction": prediction,
            "processing_time_ms": processing_time,
            "algorithm": "ml_prediction"
        }

    except ValueError as e:
        # No active model - return basic prediction
        return {
            "request_number": request.request_number,
            "executor_id": request.executor_id,
            "prediction": {
                "success_probability": 0.75,  # Default estimate
                "predicted_success": True,
                "confidence": 0.5,
                "model_id": "fallback",
                "message": "No ML model available, using fallback estimation"
            },
            "processing_time_ms": 5,
            "algorithm": "fallback_estimation"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )


@router.post("/assignments/ml-assign", response_model=Dict)
async def ml_powered_assignment(
    request: AssignmentRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """ML-powered assignment with fallback to basic rules"""
    try:
        start_time = time.time()

        # Try ML-powered assignment first
        try:
            # Get available executors (mock for now)
            available_executors = [
                {"executor_id": 1, "efficiency_score": 85.0, "district": "Чиланзар"},
                {"executor_id": 2, "efficiency_score": 78.0, "district": "Юнусабад"},
                {"executor_id": 3, "efficiency_score": 92.0, "district": "Мирзо-Улугбек"},
            ]

            best_executor = None
            best_score = 0.0
            ml_predictions = []

            # Evaluate each executor with ML
            for executor in available_executors:
                features = {
                    "specialization_match": True,  # Simplified
                    "efficiency_score": executor["efficiency_score"],
                    "urgency": request.urgency,
                    "district_match": request.address and executor["district"] in (request.address or ""),
                    "workload": 3,  # Mock current workload
                    "hour_of_day": 14,
                    "day_of_week": 2
                }

                prediction = await ml_pipeline.predict_assignment_success(features)
                ml_predictions.append({
                    "executor_id": executor["executor_id"],
                    "prediction": prediction
                })

                if prediction["success_probability"] > best_score:
                    best_score = prediction["success_probability"]
                    best_executor = executor

            if best_executor and best_score > 0.6:  # ML confidence threshold
                processing_time = int((time.time() - start_time) * 1000)

                return {
                    "request_number": request.request_number,
                    "success": True,
                    "executor_id": best_executor["executor_id"],
                    "algorithm": "ml_powered",
                    "score": best_score,
                    "confidence": best_score,
                    "ml_predictions": ml_predictions,
                    "processing_time_ms": processing_time,
                    "fallback_used": False
                }

        except Exception as ml_error:
            # ML failed, fall back to basic rules
            pass

        # Fallback to basic rules
        from app.services.smart_dispatcher import SmartDispatcher
        dispatcher = SmartDispatcher()
        basic_result = await dispatcher.assign_basic(request)

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "request_number": request.request_number,
            "success": basic_result.success,
            "executor_id": basic_result.executor_id,
            "algorithm": "fallback_basic_rules",
            "score": basic_result.score,
            "factors": basic_result.factors,
            "processing_time_ms": processing_time,
            "fallback_used": True,
            "fallback_reason": "ML prediction failed or confidence too low"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Assignment failed: {str(e)}"
        )


@router.get("/ml/models", response_model=List[Dict])
async def list_ml_models() -> List[Dict]:
    """List all available ML models"""
    try:
        models = await ml_pipeline.list_models()
        return models

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list models: {str(e)}"
        )


@router.get("/ml/models/{model_id}")
async def get_model_info(model_id: str) -> Dict:
    """Get detailed information about a specific model"""
    try:
        model_info = await ml_pipeline.get_model_info(model_id)
        return model_info

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Model not found: {str(e)}"
        )


@router.get("/ml/status")
async def get_ml_status() -> Dict:
    """Get ML pipeline status"""
    try:
        active_model = await ml_pipeline.get_model_info()
        health = await ml_pipeline.health_check()

        return {
            "ml_enabled": True,
            "pipeline_status": health,
            "active_model": active_model,
            "total_models": len(await ml_pipeline.list_models()),
            "features": {
                "training": True,
                "prediction": True,
                "model_versioning": True,
                "fallback": True
            }
        }

    except Exception as e:
        return {
            "ml_enabled": False,
            "pipeline_status": f"error: {str(e)}",
            "active_model": None,
            "error": str(e)
        }


@router.post("/data/generate")
async def generate_training_data(
    request: DataGenerationRequest
) -> Dict:
    """Generate synthetic training data"""
    try:
        start_time = time.time()

        # Generate assignments
        assignments = await data_generator.generate_historical_assignments(
            count=request.count
        )

        # Export in requested format
        dataset = await data_generator.export_training_dataset(
            assignments,
            format=request.export_format
        )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "generated_assignments": len(assignments),
            "export_format": request.export_format,
            "dataset_info": {
                "total_samples": dataset.get("sample_count", len(assignments)),
                "positive_samples": dataset.get("positive_samples", 0),
                "negative_samples": dataset.get("negative_samples", 0),
                "features": dataset.get("feature_names", [])
            },
            "processing_time_ms": processing_time,
            "status": "generated"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Data generation failed: {str(e)}"
        )


@router.post("/ml/retrain")
async def retrain_active_model(background_tasks: BackgroundTasks) -> Dict:
    """Retrain the active model with fresh data"""
    try:
        # Run retraining in background
        background_tasks.add_task(ml_pipeline.retrain_active_model)

        return {
            "status": "retraining_started",
            "message": "Model retraining started in background"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Retraining failed: {str(e)}"
        )