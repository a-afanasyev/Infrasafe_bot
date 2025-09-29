# ML Pipeline Infrastructure
# UK Management Bot - AI Service Stage 2

import asyncio
import logging
import joblib
import json
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler

from app.services.data_generator import DataGeneratorService

logger = logging.getLogger(__name__)


class MLPipelineService:
    """
    Stage 2: ML Pipeline Infrastructure
    Handles model training, versioning, and prediction
    Ready for real data when available
    """

    def __init__(self, model_path: str = "/app/models"):
        self.model_path = Path(model_path)
        self.model_path.mkdir(exist_ok=True)

        self.data_generator = DataGeneratorService()
        self.scaler = StandardScaler()

        # Current active model
        self.active_model = None
        self.active_model_id = None
        self.active_model_metadata = None

        # Model registry
        self.model_registry = {}

        # ML Configuration
        self.ml_config = {
            "min_training_samples": 100,
            "test_size": 0.2,
            "random_state": 42,
            "model_params": {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 5,
                "min_samples_leaf": 2,
                "random_state": 42
            }
        }

    async def initialize_ml_pipeline(self, use_synthetic_data: bool = True) -> Dict[str, Any]:
        """Initialize ML pipeline with data"""
        try:
            logger.info("Initializing ML Pipeline...")

            if use_synthetic_data:
                # Generate synthetic training data
                logger.info("Generating synthetic training data...")
                assignments = await self.data_generator.generate_historical_assignments(count=500)
                dataset = await self.data_generator.export_training_dataset(assignments)
            else:
                # TODO: Load real data from database
                logger.info("Loading real training data from database...")
                dataset = await self._load_real_training_data()

            # Validate dataset
            if dataset["sample_count"] < self.ml_config["min_training_samples"]:
                raise ValueError(f"Insufficient training data: {dataset['sample_count']} < {self.ml_config['min_training_samples']}")

            # Train initial model
            model_id = await self.train_model(dataset)

            return {
                "status": "initialized",
                "model_id": model_id,
                "training_samples": dataset["sample_count"],
                "data_source": "synthetic" if use_synthetic_data else "real",
                "features": dataset["feature_names"]
            }

        except Exception as e:
            logger.error(f"Failed to initialize ML pipeline: {e}")
            raise

    async def train_model(
        self,
        dataset: Dict[str, Any],
        model_type: str = "success_prediction"
    ) -> str:
        """Train ML model and save with versioning"""
        try:
            start_time = datetime.now()
            model_id = f"{model_type}_{start_time.strftime('%Y%m%d_%H%M%S')}"

            logger.info(f"Training model {model_id}...")

            # Prepare data
            X = np.array(dataset["features"])
            y = np.array(dataset["labels"])

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=self.ml_config["test_size"],
                random_state=self.ml_config["random_state"],
                stratify=y
            )

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train model
            model = RandomForestClassifier(**self.ml_config["model_params"])
            model.fit(X_train_scaled, y_train)

            # Evaluate model
            y_pred = model.predict(X_test_scaled)
            y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]

            metrics = {
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred, average='weighted'),
                "recall": recall_score(y_test, y_pred, average='weighted'),
                "f1_score": f1_score(y_test, y_pred, average='weighted'),
                "training_samples": len(X_train),
                "test_samples": len(X_test),
                "positive_rate": np.mean(y_train)
            }

            training_duration = (datetime.now() - start_time).total_seconds()

            # Model metadata
            model_metadata = {
                "id": model_id,
                "name": f"Assignment Success Predictor",
                "version": "1.0.0",
                "model_type": model_type,
                "algorithm": "RandomForest",
                "trained_at": start_time.isoformat(),
                "training_duration_seconds": training_duration,
                "metrics": metrics,
                "feature_names": dataset["feature_names"],
                "training_config": self.ml_config,
                "data_source": "synthetic",
                "is_active": False
            }

            # Save model and metadata
            await self._save_model(model_id, model, model_metadata)
            await self._save_scaler(model_id, self.scaler)

            # Register model
            self.model_registry[model_id] = model_metadata

            logger.info(f"Model {model_id} trained successfully with accuracy: {metrics['accuracy']:.3f}")

            return model_id

        except Exception as e:
            logger.error(f"Model training failed: {e}")
            raise

    async def activate_model(self, model_id: str) -> bool:
        """Activate model for production use"""
        try:
            if model_id not in self.model_registry:
                raise ValueError(f"Model {model_id} not found in registry")

            # Load model
            model, scaler = await self._load_model(model_id)
            metadata = self.model_registry[model_id]

            # Deactivate current model
            if self.active_model_id:
                self.model_registry[self.active_model_id]["is_active"] = False

            # Activate new model
            self.active_model = model
            self.active_model_id = model_id
            self.active_model_metadata = metadata
            self.scaler = scaler

            # Update registry
            self.model_registry[model_id]["is_active"] = True
            self.model_registry[model_id]["activated_at"] = datetime.now().isoformat()

            logger.info(f"Activated model {model_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to activate model {model_id}: {e}")
            return False

    async def predict_assignment_success(
        self,
        features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Predict assignment success probability"""
        try:
            if not self.active_model:
                raise ValueError("No active model available")

            # Convert features to vector
            feature_vector = self._extract_features(features)

            # Scale features
            feature_vector_scaled = self.scaler.transform([feature_vector])

            # Predict
            prediction_proba = self.active_model.predict_proba(feature_vector_scaled)[0]
            prediction_binary = self.active_model.predict(feature_vector_scaled)[0]

            # Get feature importance
            feature_importance = dict(zip(
                self.active_model_metadata["feature_names"],
                self.active_model.feature_importances_
            ))

            return {
                "success_probability": float(prediction_proba[1]),
                "predicted_success": bool(prediction_binary),
                "confidence": float(max(prediction_proba)),
                "model_id": self.active_model_id,
                "feature_importance": feature_importance,
                "features_used": features
            }

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise

    def _extract_features(self, features: Dict[str, Any]) -> List[float]:
        """Extract feature vector from request data"""
        return [
            1.0 if features.get("specialization_match", False) else 0.0,
            features.get("efficiency_score", 50.0) / 100.0,
            features.get("urgency", 3) / 5.0,
            1.0 if features.get("district_match", False) else 0.0,
            features.get("workload", 5) / 10.0,
            features.get("hour_of_day", 12) / 24.0,
            features.get("day_of_week", 3) / 7.0
        ]

    async def _save_model(self, model_id: str, model: Any, metadata: Dict) -> None:
        """Save model and metadata to disk"""
        model_dir = self.model_path / model_id
        model_dir.mkdir(exist_ok=True)

        # Save model
        model_file = model_dir / "model.joblib"
        joblib.dump(model, model_file)

        # Save metadata
        metadata_file = model_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    async def _save_scaler(self, model_id: str, scaler: Any) -> None:
        """Save scaler for model"""
        model_dir = self.model_path / model_id
        scaler_file = model_dir / "scaler.joblib"
        joblib.dump(scaler, scaler_file)

    async def _load_model(self, model_id: str) -> Tuple[Any, Any]:
        """Load model and scaler from disk"""
        model_dir = self.model_path / model_id

        model_file = model_dir / "model.joblib"
        scaler_file = model_dir / "scaler.joblib"

        if not model_file.exists() or not scaler_file.exists():
            raise FileNotFoundError(f"Model files not found for {model_id}")

        model = joblib.load(model_file)
        scaler = joblib.load(scaler_file)

        return model, scaler

    async def _load_real_training_data(self) -> Dict[str, Any]:
        """Load real training data from database (placeholder)"""
        # TODO: Implement real data loading
        logger.warning("Real data loading not implemented, using synthetic data")
        assignments = await self.data_generator.generate_historical_assignments(count=200)
        return await self.data_generator.export_training_dataset(assignments)

    async def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """Get model information"""
        if model_id:
            if model_id not in self.model_registry:
                raise ValueError(f"Model {model_id} not found")
            return self.model_registry[model_id]

        # Return active model info
        if self.active_model_id:
            return self.active_model_metadata

        return {"error": "No active model"}

    async def list_models(self) -> List[Dict[str, Any]]:
        """List all available models"""
        return list(self.model_registry.values())

    async def retrain_active_model(self) -> str:
        """Retrain the active model with fresh data"""
        try:
            logger.info("Retraining active model with fresh data...")

            # Generate fresh synthetic data
            assignments = await self.data_generator.generate_historical_assignments(count=600)
            dataset = await self.data_generator.export_training_dataset(assignments)

            # Train new model
            new_model_id = await self.train_model(dataset)

            # Auto-activate if performance is better
            new_model = self.model_registry[new_model_id]
            if self.active_model_metadata:
                old_accuracy = self.active_model_metadata["metrics"]["accuracy"]
                new_accuracy = new_model["metrics"]["accuracy"]

                if new_accuracy > old_accuracy:
                    await self.activate_model(new_model_id)
                    logger.info(f"Auto-activated new model (accuracy: {new_accuracy:.3f} > {old_accuracy:.3f})")
                else:
                    logger.info(f"Kept old model (accuracy: {old_accuracy:.3f} > {new_accuracy:.3f})")
            else:
                await self.activate_model(new_model_id)

            return new_model_id

        except Exception as e:
            logger.error(f"Model retraining failed: {e}")
            raise

    async def health_check(self) -> str:
        """Health check for ML Pipeline"""
        try:
            if not self.active_model:
                return "warning: no active model"

            # Test prediction
            test_features = {
                "specialization_match": True,
                "efficiency_score": 85.0,
                "urgency": 3,
                "district_match": True,
                "workload": 2,
                "hour_of_day": 14,
                "day_of_week": 2
            }

            result = await self.predict_assignment_success(test_features)

            if "success_probability" not in result:
                return "unhealthy: prediction failed"

            return "healthy"

        except Exception as e:
            logger.error(f"ML Pipeline health check failed: {e}")
            return f"unhealthy: {str(e)}"