# 🤖 AI Service Integration for Shift Planning - Task List & API Specification

**Document**: AI Service requirements for Sprint 14-15 Shift Planning integration
**Created**: September 30, 2025
**Status**: Task 14 Completion Required BEFORE Sprint 14-15

---

## 🚨 КРИТИЧЕСКИЕ ПРЕДУСЛОВИЯ

### **AI Service Task 14 Completion Checklist:**
Согласно MemoryBank/tasks.md:540-544, необходимо завершить ДО начала Sprint 14-15:

```yaml
ОБЯЗАТЕЛЬНЫЕ ЗАДАЧИ:
- [ ] 🔧 Реализация SQLAlchemy persistence layer
- [ ] 🔧 Исправление service integration endpoints
- [ ] 🔧 Подключение ML/geo/production endpoints к main app
- [ ] 🔧 Замена synthetic data на real data pipeline
- [ ] 🔧 Достижение Stage 4 Production Ready status

ТЕКУЩИЙ СТАТУС (критический):
- ❌ GeoOptimizer оптимизирует маршруты - НЕ РЕАЛИЗОВАНО (mock data only)
- ❌ WorkloadPredictor дает базовые прогнозы - НЕ РЕАЛИЗОВАНО (synthetic data only)
- ❌ AI Service Stage 4 Production Ready - НЕ РЕАЛИЗОВАНО (Stage 1 только)
- ❌ ML Pipeline с 88% accuracy - НЕ РЕАЛИЗОВАНО (synthetic data, no persistence)
- ❌ Circuit Breaker и Fallback Systems - НЕ РЕАЛИЗОВАНО (permanent fallback mode)
```

---

## 📋 AI SERVICE TASKS FOR SHIFT INTEGRATION

### **Phase 1: Infrastructure & Persistence (Days 1-3)**

#### Task 1: SQLAlchemy Persistence Layer
```yaml
Priority: 🔴 CRITICAL
Description: Implement database persistence for AI models and predictions
Requirements:
  - Model state persistence (genetic algorithm populations)
  - Prediction history storage (workload, assignments)
  - Training data persistence
  - Model versioning system

Implementation:
  - ai_service/models/prediction_history.py
  - ai_service/models/model_state.py
  - ai_service/models/training_data.py
  - SQLAlchemy migration scripts

Testing:
  - [ ] Model state save/load functionality
  - [ ] Prediction history retrieval
  - [ ] Database migration rollback procedures
```

#### Task 2: Real Data Pipeline Integration
```yaml
Priority: 🔴 CRITICAL
Description: Replace synthetic data with real production data
Requirements:
  - Connect to production shift data
  - Real executor performance metrics
  - Actual geographical data
  - Historical assignment success rates

Implementation:
  - ai_service/data/real_data_connector.py
  - ai_service/pipelines/data_ingestion.py
  - Data validation and quality checks
  - Fallback mechanisms for data unavailability

Testing:
  - [ ] Real data ingestion pipeline
  - [ ] Data quality validation
  - [ ] Fallback to synthetic data when needed
```

### **Phase 2: ML Model Enhancement (Days 4-6)**

#### Task 3: GeoOptimizer Production Implementation
```yaml
Priority: 🔴 CRITICAL
Description: Implement production-ready geographical optimization
Requirements:
  - Real coordinate-based optimization
  - Route calculation algorithms
  - Distance matrix optimization
  - Travel time predictions

Implementation:
  - ai_service/optimizers/geo_optimizer.py (production version)
  - ai_service/utils/distance_calculator.py
  - ai_service/utils/route_planner.py
  - Integration with mapping services (if available)

API Endpoint: POST /api/v1/optimize/geographical
Testing:
  - [ ] Real coordinate optimization
  - [ ] Route calculation accuracy
  - [ ] Performance with 1000+ locations
```

#### Task 4: WorkloadPredictor ML Enhancement
```yaml
Priority: 🔴 CRITICAL
Description: Implement ML-based workload prediction with real data
Requirements:
  - Historical workload pattern analysis
  - Seasonal factor calculations
  - Executor capacity prediction
  - Demand forecasting

Implementation:
  - ai_service/predictors/workload_predictor.py (ML version)
  - ai_service/ml/time_series_models.py
  - ai_service/ml/seasonal_analyzer.py
  - Model training and retraining procedures

API Endpoint: POST /api/v1/predict/workload
Testing:
  - [ ] Prediction accuracy > 75%
  - [ ] Seasonal pattern recognition
  - [ ] Real-time prediction capability
```

### **Phase 3: Service Integration (Days 7-9)**

#### Task 5: Production API Endpoints
```yaml
Priority: 🔴 CRITICAL
Description: Expose production-ready HTTP APIs for Shift Service
Requirements:
  - RESTful API design
  - Authentication integration
  - Error handling and validation
  - Performance optimization

Implementation:
  - All API endpoints listed below (see API SPECIFICATION)
  - Request/response validation
  - Rate limiting and throttling
  - Comprehensive error responses

Testing:
  - [ ] API response time < 500ms p95
  - [ ] 99.5% availability under load
  - [ ] Proper error handling
```

#### Task 6: Circuit Breaker & Fallback Systems
```yaml
Priority: 🔴 CRITICAL
Description: Implement resilience patterns for production
Requirements:
  - Circuit breaker for external dependencies
  - Graceful degradation strategies
  - Fallback to basic algorithms
  - Health check endpoints

Implementation:
  - ai_service/resilience/circuit_breaker.py
  - ai_service/resilience/fallback_strategies.py
  - ai_service/health/health_checker.py
  - Monitoring and alerting integration

Testing:
  - [ ] Circuit breaker functionality
  - [ ] Fallback algorithm activation
  - [ ] Recovery from failures
```

---

## 🔗 API SPECIFICATION FOR SHIFT SERVICE INTEGRATION

### **Base URL**: `http://ai-service:8009/api/v1`
### **Authentication**: Service-to-Service static keys (X-Service-Name + X-Service-API-Key)

### **1. Genetic Algorithm Optimization**
```yaml
POST /optimize/genetic-assignment
Description: Optimize shift assignments using genetic algorithm
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production
  Content-Type: application/json

Request Body:
{
  "shifts": [
    {
      "shift_id": "uuid",
      "date": "2025-10-01",
      "start_time": "08:00",
      "end_time": "16:00",
      "specialization_required": "plumbing",
      "location": {
        "latitude": 55.7558,
        "longitude": 37.6176
      },
      "priority": "high"
    }
  ],
  "executors": [
    {
      "executor_id": "uuid",
      "specializations": ["plumbing", "electrical"],
      "location": {
        "latitude": 55.7500,
        "longitude": 37.6000
      },
      "availability": {
        "date": "2025-10-01",
        "start_time": "07:00",
        "end_time": "19:00"
      },
      "current_workload": 0.7,
      "performance_rating": 4.2
    }
  ],
  "optimization_params": {
    "weights": {
      "specialization": 0.35,
      "geography": 0.25,
      "workload": 0.20,
      "rating": 0.15,
      "urgency": 0.05
    },
    "population_size": 100,
    "generations": 50
  }
}

Response:
{
  "success": true,
  "optimization_id": "uuid",
  "assignments": [
    {
      "shift_id": "uuid",
      "executor_id": "uuid",
      "confidence_score": 0.87,
      "travel_time_minutes": 15,
      "assignment_reasoning": {
        "specialization_match": 0.95,
        "geography_score": 0.80,
        "workload_balance": 0.85,
        "overall_fitness": 0.87
      }
    }
  ],
  "algorithm_stats": {
    "generations_completed": 45,
    "best_fitness": 0.89,
    "convergence_reached": true,
    "processing_time_ms": 1250
  },
  "fallback_used": false
}

Error Response:
{
  "success": false,
  "error": {
    "code": "OPTIMIZATION_FAILED",
    "message": "Genetic algorithm failed to converge",
    "details": "Population size too small for problem complexity",
    "fallback_available": true
  }
}
```

### **2. Workload Prediction**
```yaml
POST /predict/workload
Description: Predict future workload for capacity planning
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production

Request Body:
{
  "prediction_period": {
    "start_date": "2025-10-01",
    "end_date": "2025-10-07"
  },
  "executors": ["uuid1", "uuid2", "uuid3"],
  "specializations": ["plumbing", "electrical"],
  "historical_context": {
    "include_seasonal": true,
    "include_trends": true,
    "lookback_days": 90
  }
}

Response:
{
  "success": true,
  "prediction_id": "uuid",
  "predictions": [
    {
      "date": "2025-10-01",
      "specialization": "plumbing",
      "predicted_requests": 25,
      "confidence_interval": {
        "lower": 18,
        "upper": 32,
        "confidence_level": 0.80
      },
      "capacity_recommendation": {
        "required_executors": 6,
        "coverage_percentage": 0.85,
        "risk_level": "medium"
      }
    }
  ],
  "seasonal_factors": {
    "weekly_pattern": [1.1, 1.2, 1.0, 0.9, 1.3, 0.8, 0.6],
    "monthly_trend": 1.05,
    "yearly_cycle": 0.95
  },
  "model_performance": {
    "accuracy": 0.78,
    "mae": 2.1,
    "last_training": "2025-09-28T10:00:00Z"
  }
}
```

### **3. Geographical Optimization**
```yaml
POST /optimize/geographical
Description: Optimize executor assignments based on geographical proximity
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production

Request Body:
{
  "assignments": [
    {
      "shift_id": "uuid",
      "executor_id": "uuid",
      "shift_location": {
        "latitude": 55.7558,
        "longitude": 37.6176,
        "address": "Moscow, Red Square"
      },
      "executor_location": {
        "latitude": 55.7500,
        "longitude": 37.6000,
        "address": "Moscow, Arbat Street"
      }
    }
  ],
  "optimization_criteria": {
    "minimize_travel_time": true,
    "consider_traffic": true,
    "max_travel_minutes": 60
  }
}

Response:
{
  "success": true,
  "optimization_id": "uuid",
  "optimized_assignments": [
    {
      "shift_id": "uuid",
      "executor_id": "uuid",
      "travel_metrics": {
        "distance_km": 2.8,
        "travel_time_minutes": 15,
        "traffic_factor": 1.2,
        "route_efficiency": 0.85
      },
      "cost_benefit": {
        "travel_cost": 120.50,
        "time_efficiency": 0.90,
        "carbon_footprint": 1.2
      }
    }
  ],
  "total_optimization": {
    "total_travel_time": 45,
    "average_distance": 3.2,
    "efficiency_improvement": 0.23
  }
}
```

### **4. Confidence Scoring**
```yaml
POST /score/assignment-confidence
Description: Calculate confidence scores for assignment decisions
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production

Request Body:
{
  "assignment": {
    "shift_id": "uuid",
    "executor_id": "uuid",
    "assignment_factors": {
      "specialization_match": 0.95,
      "geographical_proximity": 0.80,
      "workload_balance": 0.75,
      "executor_rating": 4.2,
      "historical_success": 0.88
    }
  },
  "context": {
    "urgency_level": "high",
    "alternative_executors": 3,
    "time_constraints": true
  }
}

Response:
{
  "success": true,
  "confidence_score": 0.87,
  "score_breakdown": {
    "specialization_confidence": 0.95,
    "location_confidence": 0.80,
    "capacity_confidence": 0.85,
    "historical_confidence": 0.88,
    "overall_risk": 0.13
  },
  "recommendations": [
    "High confidence assignment",
    "Monitor workload balance",
    "Alternative executor available if needed"
  ],
  "risk_factors": [
    "Slightly above average workload"
  ]
}
```

### **5. Multi-Factor Optimization**
```yaml
POST /optimize/multi-factor
Description: Comprehensive optimization considering all factors
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production

Request Body:
{
  "optimization_request": {
    "shifts": [...],  // Same as genetic-assignment
    "executors": [...], // Same as genetic-assignment
    "constraints": {
      "max_assignments_per_executor": 8,
      "required_coverage": 0.95,
      "max_overtime_hours": 2
    },
    "weights": {
      "specialization": 0.35,
      "geography": 0.25,
      "workload": 0.20,
      "rating": 0.15,
      "urgency": 0.05
    }
  }
}

Response:
{
  "success": true,
  "optimization_result": {
    "assignments": [...], // Same format as genetic-assignment
    "coverage_achieved": 0.97,
    "optimization_quality": 0.89,
    "constraints_satisfied": true,
    "total_processing_time_ms": 2100
  },
  "algorithm_performance": {
    "genetic_algorithm": {
      "used": true,
      "fitness_score": 0.89,
      "generations": 45
    },
    "geographical_optimization": {
      "used": true,
      "travel_time_saved": 120,
      "efficiency_gain": 0.15
    },
    "workload_balancing": {
      "used": true,
      "balance_score": 0.92,
      "overload_risk": "low"
    }
  }
}
```

### **6. Model Performance & Health**
```yaml
GET /health/models
Description: Get health status of all AI models
Headers:
  X-Service-Name: shift-service
  X-Service-API-Key: shift-service-api-key-change-in-production

Response:
{
  "success": true,
  "models_status": {
    "genetic_optimizer": {
      "status": "healthy",
      "last_training": "2025-09-25T14:00:00Z",
      "accuracy": 0.89,
      "performance_trend": "stable"
    },
    "workload_predictor": {
      "status": "healthy",
      "last_training": "2025-09-28T10:00:00Z",
      "accuracy": 0.78,
      "performance_trend": "improving"
    },
    "geo_optimizer": {
      "status": "healthy",
      "last_calibration": "2025-09-29T16:30:00Z",
      "average_error_km": 0.3,
      "performance_trend": "stable"
    }
  },
  "system_health": {
    "overall_status": "healthy",
    "circuit_breaker_status": "closed",
    "fallback_active": false,
    "processing_capacity": 0.65
  }
}

GET /metrics/performance
Description: Get detailed performance metrics
Response:
{
  "success": true,
  "performance_metrics": {
    "api_latency": {
      "p50": 120,
      "p95": 480,
      "p99": 750
    },
    "prediction_accuracy": {
      "genetic_optimization": 0.89,
      "workload_prediction": 0.78,
      "geo_optimization": 0.92
    },
    "throughput": {
      "requests_per_minute": 145,
      "concurrent_optimizations": 8
    }
  }
}
```

---

## 🔄 INTEGRATION WORKFLOW

### **Shift Service → AI Service Integration Pattern:**

```python
# Example: Shift Service calling AI Service for assignment optimization
async def optimize_shift_assignments(shifts: List[Shift], executors: List[Executor]):
    try:
        # 1. Prepare AI Service request
        ai_request = {
            "shifts": [shift.to_ai_format() for shift in shifts],
            "executors": [executor.to_ai_format() for executor in executors],
            "optimization_params": get_optimization_config()
        }

        # 2. Call AI Service with circuit breaker
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://ai-service:8009/api/v1/optimize/genetic-assignment",
                json=ai_request,
                headers={
                    "X-Service-Name": "shift-service",
                    "X-Service-API-Key": settings.AI_SERVICE_API_KEY,
                    "Content-Type": "application/json"
                },
                timeout=5.0
            )

        # 3. Process AI response
        if response.status_code == 200:
            ai_result = response.json()
            if ai_result["success"]:
                return process_ai_assignments(ai_result["assignments"])
            else:
                logger.warning(f"AI optimization failed: {ai_result['error']}")
                return fallback_to_basic_assignment(shifts, executors)
        else:
            logger.error(f"AI service error: {response.status_code}")
            return fallback_to_basic_assignment(shifts, executors)

    except Exception as e:
        logger.error(f"AI service communication failed: {e}")
        return fallback_to_basic_assignment(shifts, executors)
```

---

## ⚡ PERFORMANCE REQUIREMENTS

```yaml
API Performance Targets:
  Response Time:
    - p50: < 200ms
    - p95: < 500ms
    - p99: < 1000ms
  Availability: 99.5%
  Throughput: 100+ requests/minute
  Concurrent Processing: 10+ optimization requests

Model Performance Targets:
  Genetic Algorithm: > 85% fitness score
  Workload Prediction: > 75% accuracy
  Geographical Optimization: < 5% route error
  Confidence Scoring: 0.80+ correlation with actual success

Resource Limits:
  Memory: < 2GB per optimization
  CPU: < 80% utilization under normal load
  Processing Time: < 5 seconds for complex optimizations
```

---

## 🧪 TESTING STRATEGY

### **Unit Tests:**
- [ ] Individual algorithm functionality
- [ ] Data pipeline components
- [ ] API endpoint validation
- [ ] Error handling scenarios

### **Integration Tests:**
- [ ] Shift Service ↔ AI Service communication
- [ ] Database persistence operations
- [ ] Real data pipeline functionality
- [ ] Circuit breaker behavior

### **Performance Tests:**
- [ ] Load testing with 100+ concurrent requests
- [ ] Optimization with 1000+ shifts scenario
- [ ] Memory usage under sustained load
- [ ] API response time validation

### **Production Readiness Tests:**
- [ ] Fallback system activation
- [ ] Circuit breaker functionality
- [ ] Model retraining procedures
- [ ] Health check accuracy

---

**📝 Status**: ⚠️ **PENDING IMPLEMENTATION**
**🔄 Version**: 1.0
**📅 Deadline**: Must be completed BEFORE Sprint 14-15 starts
**🎯 Success Criteria**: All 6 tasks completed + Stage 4 Production Ready achieved
**⚡ Performance**: API < 500ms p95, Models > 75% accuracy, 99.5% availability