# PHASE 2B - QUICK REFERENCE GUIDE
## Async AI Services - Developer Reference

**Version**: 1.0
**Date**: 20.10.2025
**For**: Development Team

---

## 🚀 QUICK START

### Using AsyncAssignmentOptimizer

```python
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.async_assignment_optimizer import AsyncAssignmentOptimizer

async def optimize_assignments():
    async with AsyncSessionLocal() as session:
        optimizer = AsyncAssignmentOptimizer(session)

        # Run genetic algorithm optimization
        result = await optimizer.optimize_assignments(
            algorithm="genetic",  # or "simulated_annealing", "hybrid"
            optimization_scope="active"  # or "all", "pending"
        )

        print(f"Optimized {result.optimized_assignments} assignments")
        print(f"Improvement: {result.improvement_score:.2%}")
        print(f"Time: {result.processing_time:.2f}s")
```

### Using AsyncGeoOptimizer

```python
from uk_management_bot.services.async_geo_optimizer import AsyncGeoOptimizer, RoutePoint

async def optimize_route():
    async with AsyncSessionLocal() as session:
        optimizer = AsyncGeoOptimizer(session)

        # Define route points
        points = [
            RoutePoint(address="Location 1", priority=1),
            RoutePoint(address="Location 2", priority=2),
            RoutePoint(address="Location 3", priority=1),
        ]

        # Optimize route
        optimized_route = await optimizer.optimize_route(points)

        print(f"Total distance: {optimized_route.total_distance:.2f} km")
        print(f"Estimated time: {optimized_route.total_time:.0f} min")
```

### Using AsyncWorkloadPredictor

```python
from datetime import date, timedelta
from uk_management_bot.services.async_workload_predictor import AsyncWorkloadPredictor

async def predict_workload():
    async with AsyncSessionLocal() as session:
        predictor = AsyncWorkloadPredictor(session)

        # Single day prediction
        tomorrow = date.today() + timedelta(days=1)
        prediction = await predictor.predict_daily_requests(tomorrow)

        print(f"Predicted requests: {prediction.predicted_requests}")
        print(f"Confidence: {prediction.confidence_level:.1%}")
        print(f"Recommended shifts: {prediction.recommended_shifts}")

        # Period prediction (parallel)
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=14)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date,
            specialization="Сантехника"  # optional filter
        )

        for pred in predictions:
            print(f"{pred.date}: {pred.predicted_requests} requests")
```

---

## 📊 PERFORMANCE BENCHMARKS

### Expected Latencies

| Operation | Target | Typical | Max Acceptable |
|-----------|--------|---------|----------------|
| Single assignment | <0.5s | 0.2s | 1.0s |
| Batch optimization (50) | <3.0s | 1.5s | 5.0s |
| Route optimization (10 pts) | <1.0s | 0.5s | 2.0s |
| Daily prediction | <0.5s | 0.3s | 1.0s |
| Period prediction (14 days) | <2.0s | 1.0s | 3.0s |
| Pattern analysis (90 days) | <1.0s | 0.5s | 2.0s |

### Parallel Processing Gains

```
Sequential vs Parallel:
- Population evaluation: 50x speedup (2.5s → 0.05s)
- Distance matrix (10x10): 10x speedup (2.5s → 0.25s)
- Daily stats (90 days): 30x speedup (9.0s → 0.3s)
- Period predictions (14): 7x speedup (14.0s → 2.0s)
```

---

## 🔧 CONFIGURATION

### AsyncAssignmentOptimizer Parameters

```python
# Genetic Algorithm
POPULATION_SIZE = 50          # Number of solutions per generation
MAX_GENERATIONS = 100         # Maximum iterations
MUTATION_RATE = 0.1          # 10% mutation probability
CROSSOVER_RATE = 0.8         # 80% crossover probability
ELITE_SIZE = 5               # Top solutions preserved
STAGNATION_LIMIT = 20        # Generations without improvement

# Fitness Weights
SPECIALIZATION_WEIGHT = 0.35  # 35%
GEOGRAPHIC_WEIGHT = 0.25      # 25%
WORKLOAD_WEIGHT = 0.20       # 20%
RATING_WEIGHT = 0.15         # 15%
URGENCY_WEIGHT = 0.05        # 5%
```

### AsyncWorkloadPredictor Parameters

```python
# Historical Data
MIN_HISTORICAL_DAYS = 30     # Minimum for reliable predictions
PREDICTION_HORIZON = 14      # Days to predict ahead

# Seasonal Factors (monthly)
WINTER_FACTOR = 1.15-1.20    # Dec-Feb (higher workload)
SPRING_FACTOR = 0.85-1.00    # Mar-May
SUMMER_FACTOR = 0.75-0.85    # Jun-Aug (lower workload)
FALL_FACTOR = 0.95-1.15      # Sep-Nov

# Weekday Factors
MONDAY_FACTOR = 1.10         # Highest
WEEKEND_FACTOR = 0.60-0.70   # Lowest
```

---

## 🐛 COMMON ISSUES & SOLUTIONS

### Issue: "Event loop is closed"

**Cause**: Trying to use async code in sync context

**Solution**:
```python
# ❌ Wrong
prediction = predictor.predict_daily_requests(date.today())

# ✅ Correct
prediction = await predictor.predict_daily_requests(date.today())
```

### Issue: "Task attached to different loop"

**Cause**: Creating multiple event loops

**Solution**:
```python
# ❌ Wrong
async def worker():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# ✅ Correct
async def worker():
    # Use existing event loop
    loop = asyncio.get_event_loop()
```

### Issue: "Database session is closed"

**Cause**: Using session outside context manager

**Solution**:
```python
# ❌ Wrong
session = AsyncSessionLocal()
result = await session.execute(query)
# session closed here!

# ✅ Correct
async with AsyncSessionLocal() as session:
    result = await session.execute(query)
    # Use result here
```

### Issue: Slow predictions

**Cause**: Not enough historical data or heavy computation

**Solution**:
```python
# Check historical data availability
historical_data = await predictor._get_historical_data(
    date.today(),
    days_back=90
)
print(f"Data points: {len(historical_data.requests)}")

# If < 30 days of data, predictions will be low confidence
# Solution: Accumulate more historical data
```

---

## 📈 MONITORING

### Key Metrics to Track

```python
# Performance Metrics
assignment_latency = time_end - time_start
prediction_latency = time_end - time_start
cache_hit_rate = hits / (hits + misses)
database_query_time = query_end - query_start

# Business Metrics
assignment_success_rate = successful / total
prediction_accuracy = correct / total
user_satisfaction = positive / total_feedback
```

### Logging Best Practices

```python
import logging

logger = logging.getLogger(__name__)

# Always log operation start
logger.info(f"[ASYNC] Starting prediction for {target_date}")

# Log performance metrics
logger.debug(f"[ASYNC] Prediction completed in {elapsed:.2f}s")

# Log errors with context
logger.error(
    f"[ASYNC] Prediction failed: {str(e)}",
    extra={"target_date": target_date, "specialization": spec}
)
```

---

## 🧪 TESTING

### Unit Test Example

```python
import pytest
from uk_management_bot.services.async_workload_predictor import WorkloadPrediction

def test_workload_prediction_creation():
    """Test WorkloadPrediction dataclass"""
    prediction = WorkloadPrediction(
        date=date(2025, 10, 20),
        predicted_requests=15,
        confidence_level=0.85,
        peak_hours=[9, 10, 11],
        recommended_shifts=3,
        specialization_breakdown={"Сантехника": 10},
        factors={"seasonal": 1.2, "weekday": 1.0}
    )

    assert prediction.predicted_requests == 15
    assert 0.0 <= prediction.confidence_level <= 1.0
```

### Integration Test Example

```python
@pytest.mark.asyncio
async def test_predict_daily_requests(async_db):
    """Test daily prediction with real database"""
    predictor = AsyncWorkloadPredictor(async_db)

    # Create test data
    await create_test_requests(async_db, days=90)

    # Run prediction
    target_date = date.today() + timedelta(days=7)
    prediction = await predictor.predict_daily_requests(target_date)

    # Verify
    assert isinstance(prediction, WorkloadPrediction)
    assert prediction.predicted_requests >= 0
    assert 0.0 <= prediction.confidence_level <= 1.0
```

### Running Tests

```bash
# All async tests
docker-compose -f docker-compose.dev.yml exec app \
  pytest tests/test_async_*.py -v

# Specific test file
docker-compose -f docker-compose.dev.yml exec app \
  pytest tests/test_async_assignment_optimizer.py -v

# With coverage
docker-compose -f docker-compose.dev.yml exec app \
  pytest tests/test_async_*.py --cov=uk_management_bot/services --cov-report=html
```

---

## 🔐 SECURITY CONSIDERATIONS

### Database Session Security

```python
# ✅ Always use context managers
async with AsyncSessionLocal() as session:
    # Session automatically closed
    pass

# ✅ Never expose database credentials
# Use environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Use parameterized queries
query = select(Request).where(Request.id == request_id)
# NOT: f"SELECT * FROM requests WHERE id = {request_id}"
```

### Input Validation

```python
# ✅ Validate all inputs
def validate_date_range(start_date: date, end_date: date):
    if start_date > end_date:
        raise ValueError("Start date must be before end date")
    if (end_date - start_date).days > 365:
        raise ValueError("Date range too large (max 365 days)")

# ✅ Sanitize specialization input
ALLOWED_SPECIALIZATIONS = ["Сантехника", "Электрика", ...]
if specialization not in ALLOWED_SPECIALIZATIONS:
    raise ValueError(f"Invalid specialization: {specialization}")
```

---

## 📚 API REFERENCE

### AsyncAssignmentOptimizer

```python
class AsyncAssignmentOptimizer:
    """Genetic algorithm + Simulated annealing optimizer"""

    async def optimize_assignments(
        algorithm: str = "hybrid",
        optimization_scope: str = "active"
    ) -> OptimizationResult

    async def _genetic_algorithm_optimization(
        assignments: List[ShiftAssignment]
    ) -> Dict[str, Any]

    async def _simulated_annealing_optimization(
        assignments: List[ShiftAssignment]
    ) -> Dict[str, Any]
```

### AsyncGeoOptimizer

```python
class AsyncGeoOptimizer:
    """TSP solver + Route optimization"""

    async def optimize_route(
        points: List[RoutePoint],
        start_point: Optional[RoutePoint] = None
    ) -> OptimizedRoute

    async def calculate_distance_matrix_parallel(
        points: List[RoutePoint]
    ) -> DistanceMatrix
```

### AsyncWorkloadPredictor

```python
class AsyncWorkloadPredictor:
    """ML workload forecasting"""

    async def predict_daily_requests(
        target_date: date,
        specialization: Optional[str] = None
    ) -> WorkloadPrediction

    async def predict_period_workload(
        start_date: date,
        end_date: date,
        specialization: Optional[str] = None
    ) -> List[WorkloadPrediction]

    async def analyze_historical_patterns(
        days_back: int = 90
    ) -> Dict[str, HistoricalPattern]
```

---

## 🎓 BEST PRACTICES

### 1. Always Use Async Context Managers

```python
# ✅ Correct
async with AsyncSessionLocal() as session:
    result = await session.execute(query)

# ❌ Wrong
session = AsyncSessionLocal()
result = await session.execute(query)
session.close()  # May not execute if error occurs
```

### 2. Use asyncio.gather() for Parallel Operations

```python
# ✅ Parallel (fast)
results = await asyncio.gather(
    operation_1(),
    operation_2(),
    operation_3()
)

# ❌ Sequential (slow)
result1 = await operation_1()
result2 = await operation_2()
result3 = await operation_3()
```

### 3. Handle Exceptions Properly

```python
# ✅ Correct
try:
    prediction = await predictor.predict_daily_requests(date)
except Exception as e:
    logger.error(f"Prediction failed: {e}")
    # Return fallback or raise
    return default_prediction

# ❌ Wrong
prediction = await predictor.predict_daily_requests(date)
# No error handling - will crash on failure
```

### 4. Log Performance Metrics

```python
# ✅ Correct
import time

start = time.time()
result = await optimizer.optimize_assignments()
elapsed = time.time() - start

logger.info(f"Optimization completed in {elapsed:.2f}s")
```

### 5. Use Type Hints

```python
# ✅ Correct
async def predict(
    target_date: date,
    specialization: Optional[str] = None
) -> WorkloadPrediction:
    pass

# ❌ Wrong
async def predict(target_date, specialization=None):
    pass
```

---

## 🔗 USEFUL LINKS

- **Documentation**: `/docs/PHASE2B_FINAL_REPORT.md`
- **Test Summary**: `/docs/PHASE2B_TEST_SUMMARY.md`
- **Deployment Guide**: `/docs/PHASE2B_DEPLOYMENT_CHECKLIST.md`
- **Migration Plan**: `/docs/PHASE2B_MIGRATION_PLAN.md`

---

## 💡 TIPS & TRICKS

### Tip 1: Debugging Async Code

```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use pytest with verbose output
pytest tests/test_async_*.py -vv --log-cli-level=DEBUG

# Check event loop
import asyncio
loop = asyncio.get_event_loop()
print(f"Loop running: {loop.is_running()}")
```

### Tip 2: Performance Profiling

```python
import time
import asyncio

async def profile_operation():
    start = time.time()

    # Your async operation
    result = await some_operation()

    elapsed = time.time() - start
    print(f"Operation took {elapsed:.2f}s")

    return result
```

### Tip 3: Caching Predictions

```python
from functools import lru_cache
from datetime import date

# Cache predictions for 1 hour
@lru_cache(maxsize=128)
async def cached_prediction(target_date: date) -> WorkloadPrediction:
    # Check if cached prediction is still valid
    # If yes, return cached
    # If no, generate new prediction
    pass
```

---

**Document Version**: 1.0
**Last Updated**: 20.10.2025
**Maintained By**: Development Team

