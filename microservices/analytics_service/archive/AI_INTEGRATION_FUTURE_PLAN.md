# AI Integration Plan - Analytics Service Enhancement

**Дата создания**: 6 октября 2025
**Статус**: 📋 PLANNED - Waiting for AI Service
**Приоритет**: 🔵 MEDIUM (Post-Production Enhancement)
**Версия**: 1.0
**Связан с**: SPRINT_16_18_ANALYTICS_REVISED_PLAN.md

---

## 🎯 EXECUTIVE SUMMARY

### Context
Analytics Service будет запущен в продакшн **БЕЗ AI/ML функций** (Sprint 16-18, Week 10).
Все AI-зависимые функции заменены на **заглушки (stubs)** с простыми rule-based fallbacks.

### Goal
Интегрировать полноценный AI Service после его готовности для:
- ML-based anomaly detection (85%+ accuracy)
- Time-series predictions (MAE <20%)
- Smart alerting
- Predictive analytics

### Timeline
**Когда начать**: После готовности AI Service
**Длительность**: 2-3 недели (20-24 часа работы)
**Команда**: 1 ML engineer + 1 backend developer

---

## 🚨 WHY AI WAS DEFERRED

### Technical Reasons
1. ❌ **AI Service не существует** - требуется отдельная разработка
2. ❌ **Unrealistic targets** - 95% accuracy за 8 часов нереально
3. ❌ **Blocking dependency** - задержка AI блокирует весь Analytics Service

### Business Reasons
1. ✅ **MVP без AI работает** - core KPIs, dashboards, alerts работают
2. ✅ **Rule-based достаточно** - 60% accuracy лучше чем ничего
3. ✅ **Faster time-to-market** - продакшн на 2-3 недели раньше

### Risk Mitigation
1. ✅ **Stubs реализованы** - система не ломается без AI
2. ✅ **Clear messaging** - пользователи знают что AI "Coming Soon"
3. ✅ **Easy migration** - заменить stub на real client = 2 часа работы

---

## 📊 CURRENT STATE (Sprint 16-18 Deliverables)

### Implemented Stubs

#### 1. AIServiceClientStub
```python
# Location: analytics_service/integrations/ai_client.py

class AIServiceClientStub:
    """Заглушка для AI Service клиента"""

    async def health_check(self) -> bool:
        """Всегда возвращает False (AI не готов)"""
        return False

    async def predict(self, data: PredictionRequest) -> PredictionResponse:
        """
        Заглушка: возвращает среднее за 7 дней
        TODO: Replace with real AI Service call
        """
        return PredictionResponse(
            predictions=[avg_7d] * 7,
            confidence=0.0,
            method="fallback_average",
            warning="⚠️ AI Service not ready. Showing 7-day average.",
            ai_ready=False
        )

    async def detect_anomaly(
        self, data: AnomalyDetectionRequest
    ) -> AnomalyDetectionResponse:
        """
        Заглушка: rule-based detection
        TODO: Replace with ML-based detection
        """
        return AnomalyDetectionResponse(
            error="AI_SERVICE_NOT_READY",
            fallback="using_threshold_based_detection",
            accuracy=0.60  # Rule-based, NOT ML
        )
```

#### 2. AnomalyDetectorStub
```python
# Location: analytics_service/services/anomaly_detector.py

class AnomalyDetectorStub:
    """Rule-based anomaly detection (60% accuracy)"""

    async def detect_anomalies(
        self, metric_name: str, period: str = "7d"
    ) -> List[Anomaly]:
        """
        Simple rule: value > max_last_7d * 1.5 = anomaly
        TODO: Replace with ML z-score/isolation forest
        """
        recent_max = await self._get_period_max(metric_name, period)
        current = await self._get_current_value(metric_name)

        if current > recent_max * 1.5:
            return [
                Anomaly(
                    metric=metric_name,
                    value=current,
                    threshold=recent_max * 1.5,
                    severity="warning",
                    method="rule_based",  # NOT ML
                    confidence=0.60,
                    message="⚠️ Rule-based detection (AI not ready)"
                )
            ]
        return []
```

#### 3. PredictorStub
```python
# Location: analytics_service/services/predictor.py

class PredictorStub:
    """Simple average-based prediction (0% ML accuracy)"""

    async def predict_7_days(self, metric_name: str) -> PredictionResult:
        """
        Прогноз = среднее за последние 7 дней (константа)
        TODO: Replace with linear regression / ARIMA / LSTM
        """
        avg_7d = await self._calculate_7day_average(metric_name)

        return PredictionResult(
            predictions=[avg_7d] * 7,  # Flat line
            dates=self._next_7_days(),
            confidence=0.0,
            mae=None,  # Cannot calculate MAE
            method="simple_average",
            warning="⚠️ AI predictions unavailable. Showing 7-day average.",
            ai_ready=False
        )
```

### API Endpoints with Stubs

#### Current Behavior
```yaml
GET /api/v1/analytics/anomalies:
  Returns:
    - Rule-based anomaly flags (60% accuracy)
    - Warning: "AI-based detection coming soon"
    - Fallback method: threshold-based

GET /api/v1/analytics/predictions/{metric}:
  Returns:
    - 7-day average as "prediction"
    - confidence: 0.0
    - Warning: "AI Service not ready"
    - Fallback method: simple average

POST /api/v1/analytics/ai/health:
  Returns:
    - {"ai_ready": false}
    - {"message": "AI Service integration pending"}
```

---

## 🚀 FUTURE AI INTEGRATION PLAN

### Prerequisites

#### 1. AI Service Must Provide
```yaml
Endpoints Required:
  POST /api/v1/ai/predict:
    Input: {metric_name, historical_data[], period}
    Output: {predictions[], confidence, mae}

  POST /api/v1/ai/detect-anomaly:
    Input: {metric_name, data_points[], threshold}
    Output: {anomalies[], confidence, method}

  GET /api/v1/ai/health:
    Output: {status, models_loaded, version}

Performance:
  ✅ Response time <500ms (p95)
  ✅ 100 req/sec capacity
  ✅ 99% uptime

Models:
  ✅ Anomaly detection model trained (85%+ accuracy)
  ✅ Time-series prediction model (MAE <20%)
  ✅ Models versioned and deployable
```

#### 2. Analytics Service Preparation
```yaml
Already Done (Sprint 16-18):
  ✅ Stubs implemented and tested
  ✅ API contracts defined
  ✅ Error handling in place
  ✅ Fallback mechanisms working

To Be Done (AI Integration Sprint):
  ⏳ Replace stubs with real AI client
  ⏳ Add circuit breaker pattern
  ⏳ Implement A/B testing framework
  ⏳ Add model versioning support
```

---

## 📋 AI INTEGRATION SPRINT (2-3 Weeks)

### Week 1: AI Service Integration (8 hours)

#### Task 1.1: Real AI Client Implementation (4h)
```python
# Replace: analytics_service/integrations/ai_client.py

class AIServiceClient:
    """Real AI Service HTTP client"""

    def __init__(self, base_url: str, timeout: int = 5):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=timeout)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )

    async def health_check(self) -> bool:
        """Check AI Service availability"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def predict(self, data: PredictionRequest) -> PredictionResponse:
        """
        Call AI Service for ML predictions
        Fallback to stub if AI unavailable
        """
        if not await self.health_check():
            logger.warning("AI Service unavailable, using fallback")
            return await self.fallback_predict(data)

        try:
            response = await self.circuit_breaker.call(
                self.client.post,
                f"{self.base_url}/predict",
                json=data.dict()
            )
            return PredictionResponse(**response.json())
        except CircuitBreakerOpen:
            logger.error("Circuit breaker open, using fallback")
            return await self.fallback_predict(data)

    async def fallback_predict(self, data: PredictionRequest):
        """Fallback to stub when AI fails"""
        stub = PredictorStub()
        return await stub.predict_7_days(data.metric_name)
```

**Deliverables**:
- ✅ Real AI Service client implemented
- ✅ Circuit breaker pattern (prevent cascade failures)
- ✅ Fallback to stubs when AI unavailable
- ✅ Retry logic (3 attempts, exponential backoff)

#### Task 1.2: Error Handling & Resilience (2h)
```yaml
Features:
  - Circuit breaker (5 failures → open for 60s)
  - Retry with exponential backoff (1s, 2s, 4s)
  - Request timeout (5 seconds)
  - Graceful degradation to stubs
  - Metrics: ai_request_duration, ai_failures_total

Deliverables:
  ✅ Circuit breaker tested
  ✅ Fallback works seamlessly
  ✅ No cascading failures
  ✅ Prometheus metrics added
```

#### Task 1.3: Integration Tests (2h)
```python
# tests/integration/test_ai_integration.py

async def test_ai_service_prediction():
    """Test real AI Service prediction call"""
    client = AIServiceClient(base_url=AI_SERVICE_URL)

    result = await client.predict(
        PredictionRequest(
            metric_name="requests_total",
            period="7d"
        )
    )

    assert result.confidence > 0.0
    assert len(result.predictions) == 7
    assert result.method == "ml_based"
    assert result.ai_ready is True

async def test_ai_service_unavailable_fallback():
    """Test fallback when AI Service down"""
    client = AIServiceClient(base_url="http://invalid:9999")

    result = await client.predict(
        PredictionRequest(metric_name="requests_total", period="7d")
    )

    # Should fallback to stub
    assert result.confidence == 0.0
    assert result.method == "fallback_average"
    assert result.ai_ready is False
```

**Deliverables**:
- ✅ Integration tests with real AI Service
- ✅ Fallback tests when AI down
- ✅ Circuit breaker tests
- ✅ 80%+ test coverage

---

### Week 2: ML Anomaly Detection (8 hours)

#### Task 2.1: Replace AnomalyDetectorStub (4h)
```python
# analytics_service/services/anomaly_detector.py

class AnomalyDetectorML:
    """ML-based anomaly detection (85%+ accuracy)"""

    def __init__(self, ai_client: AIServiceClient):
        self.ai_client = ai_client
        self.fallback = AnomalyDetectorStub()  # Keep stub as fallback

    async def detect_anomalies(
        self, metric_name: str, period: str = "7d"
    ) -> List[Anomaly]:
        """
        Use AI Service for ML-based anomaly detection
        Fallback to rule-based if AI unavailable
        """
        data_points = await self._get_historical_data(metric_name, period)

        try:
            response = await self.ai_client.detect_anomaly(
                AnomalyDetectionRequest(
                    metric_name=metric_name,
                    data_points=data_points,
                    sensitivity="medium"
                )
            )

            return [
                Anomaly(
                    metric=metric_name,
                    value=a.value,
                    threshold=a.threshold,
                    severity=a.severity,
                    method="ml_based",  # NOW ML!
                    confidence=a.confidence,  # 0.85+
                    message=f"ML anomaly detected (confidence: {a.confidence:.0%})"
                )
                for a in response.anomalies
            ]
        except Exception as e:
            logger.warning(f"ML detection failed: {e}, using fallback")
            return await self.fallback.detect_anomalies(metric_name, period)
```

**Deliverables**:
- ✅ ML-based anomaly detection working
- ✅ 85%+ accuracy (validated on test data)
- ✅ Fallback to rule-based if AI fails
- ✅ Confidence scores returned

#### Task 2.2: A/B Testing Framework (2h)
```yaml
Goal: Gradual rollout of ML vs rule-based

Implementation:
  - Feature flag: ai_anomaly_detection_enabled (default: false)
  - Gradual rollout: 10% → 50% → 100%
  - Compare accuracy: ML vs rule-based
  - Metrics: precision, recall, F1-score

Config:
  feature_flags:
    ai_anomaly_detection:
      enabled: true
      rollout_percentage: 10  # Start with 10%
      fallback_on_error: true

Deliverables:
  ✅ Feature flag system implemented
  ✅ 10% traffic to ML, 90% to rule-based
  ✅ Metrics compared (ML vs rule-based)
  ✅ Dashboard showing accuracy comparison
```

#### Task 2.3: Validation & Tuning (2h)
```yaml
Validation:
  - Use historical data with known anomalies
  - Calculate: precision, recall, F1-score
  - Target: 85%+ accuracy (F1-score)

Tuning:
  - Adjust sensitivity parameter
  - Test different models (z-score, isolation forest, LSTM)
  - Document optimal settings

Deliverables:
  ✅ Accuracy validated (85%+ F1-score)
  ✅ Model tuned for production
  ✅ Documentation updated
```

---

### Week 3: ML Predictions & Production (8 hours)

#### Task 3.1: Replace PredictorStub (4h)
```python
# analytics_service/services/predictor.py

class PredictorML:
    """ML-based time-series predictions (MAE <20%)"""

    def __init__(self, ai_client: AIServiceClient):
        self.ai_client = ai_client
        self.fallback = PredictorStub()

    async def predict_7_days(self, metric_name: str) -> PredictionResult:
        """
        Use AI Service for ML predictions
        Fallback to average if AI unavailable
        """
        historical_data = await self._get_30day_history(metric_name)

        try:
            response = await self.ai_client.predict(
                PredictionRequest(
                    metric_name=metric_name,
                    historical_data=historical_data,
                    period="7d",
                    model="linear_regression"  # or ARIMA, LSTM
                )
            )

            return PredictionResult(
                predictions=response.predictions,
                dates=self._next_7_days(),
                confidence=response.confidence,  # 0.8+
                mae=response.mae,  # <20%
                method="ml_based",
                warning=None,  # No warning!
                ai_ready=True
            )
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}, using fallback")
            return await self.fallback.predict_7_days(metric_name)
```

**Deliverables**:
- ✅ ML predictions working (linear regression)
- ✅ MAE <20% (validated)
- ✅ 7-day forecast accuracy measured
- ✅ Fallback to average if AI fails

#### Task 3.2: Model Versioning (2h)
```yaml
Goal: Support multiple AI models

Implementation:
  - Model version in API response
  - A/B test different models
  - Rollback to previous model if accuracy drops

Models to support:
  - linear_regression (baseline)
  - arima (seasonal data)
  - lstm (complex patterns)

Config:
  ai_models:
    predictions:
      default: "linear_regression"
      available: ["linear_regression", "arima", "lstm"]
      min_accuracy: 0.80  # MAE <20%

Deliverables:
  ✅ Model selection via API parameter
  ✅ Multiple models supported
  ✅ Model performance tracked
  ✅ Auto-rollback if accuracy <80%
```

#### Task 3.3: Production Deployment (2h)
```yaml
Deployment Strategy:
  1. Deploy new AI-enabled code (feature flag OFF)
  2. Enable AI for 10% of requests
  3. Monitor for 24 hours
  4. If success: 50% → 100%
  5. If failure: rollback to stubs

Go-Live Checklist:
  - [ ] AI Service health check passes
  - [ ] Circuit breaker tested
  - [ ] Fallback to stubs works
  - [ ] Accuracy validated (85%+ anomaly, MAE <20% predictions)
  - [ ] Metrics dashboard ready
  - [ ] Runbook updated

Deliverables:
  ✅ AI features in production
  ✅ Gradual rollout successful
  ✅ Monitoring dashboard ready
  ✅ Documentation updated
```

---

## 📊 SUCCESS METRICS

### Technical Metrics
```yaml
Anomaly Detection:
  ✅ Accuracy (F1-score): 85%+ (was 60%)
  ✅ False positive rate: <10%
  ✅ Detection latency: <1 second
  ✅ Fallback to rule-based: <5% of requests

Predictions:
  ✅ MAE: <20% (was N/A)
  ✅ Confidence: 80%+ average
  ✅ 7-day forecast accuracy: 85%+
  ✅ Fallback to average: <5% of requests

Reliability:
  ✅ AI Service uptime: 99%+
  ✅ Circuit breaker trips: <1% of requests
  ✅ Fallback works seamlessly
  ✅ No cascading failures
```

### Business Metrics
```yaml
User Impact:
  ✅ Anomaly alerts more accurate (fewer false alarms)
  ✅ Predictions help capacity planning
  ✅ Users see "AI-powered" instead of "Coming Soon"
  ✅ Trust in analytics increases

Operational:
  ✅ Manual anomaly investigation reduced 50%
  ✅ Proactive capacity planning enabled
  ✅ Incident response time reduced 30%
```

---

## 🚨 RISKS & MITIGATION

### Risk 1: AI Service Delays
**Probability**: High (60%)
**Impact**: Medium - Delays AI features, но Analytics работает без AI

**Mitigation**:
- ✅ Stubs уже в продакшне
- ✅ No blocking dependency
- ✅ Can wait for AI Service без последствий

### Risk 2: AI Accuracy Below Targets
**Probability**: Medium (40%)
**Impact**: Medium - Нужна переработка моделей

**Mitigation**:
- ✅ Start with 10% rollout (A/B test)
- ✅ Keep rule-based as fallback
- ✅ Tune models before 100% rollout
- ✅ Auto-rollback if accuracy <threshold

### Risk 3: AI Service Instability
**Probability**: Medium (30%)
**Impact**: Low - Fallback to stubs работает

**Mitigation**:
- ✅ Circuit breaker prevents cascade failures
- ✅ Automatic fallback to stubs
- ✅ Monitoring alerts if fallback rate >5%
- ✅ Can disable AI with feature flag

---

## 📋 TASK CHECKLIST

### Week 1: AI Service Integration (8h)
- [ ] Task 1.1: Implement AIServiceClient (4h)
- [ ] Task 1.2: Error handling + circuit breaker (2h)
- [ ] Task 1.3: Integration tests (2h)

### Week 2: ML Anomaly Detection (8h)
- [ ] Task 2.1: Replace AnomalyDetectorStub with ML (4h)
- [ ] Task 2.2: A/B testing framework (2h)
- [ ] Task 2.3: Validation & tuning (2h)

### Week 3: ML Predictions & Production (8h)
- [ ] Task 3.1: Replace PredictorStub with ML (4h)
- [ ] Task 3.2: Model versioning (2h)
- [ ] Task 3.3: Production deployment (2h)

**Total**: 24 hours (2-3 weeks with 1-2 developers)

---

## 🎯 GO/NO-GO CRITERIA

### Prerequisites to Start
```yaml
MUST HAVE:
  ✅ AI Service deployed and accessible
  ✅ AI Service health check passing
  ✅ Anomaly detection endpoint working
  ✅ Prediction endpoint working
  ✅ AI Service capacity: 100+ req/sec
  ✅ Analytics Service stubs in production

NICE TO HAVE:
  ✅ AI models pre-trained
  ✅ Historical data ready for validation
  ✅ Monitoring dashboard prepared
```

### Go-Live Criteria (Week 3)
```yaml
GO to Production:
  ✅ Anomaly detection accuracy ≥85% (F1-score)
  ✅ Prediction MAE ≤20%
  ✅ Circuit breaker tested and working
  ✅ Fallback to stubs working seamlessly
  ✅ 10% rollout successful (24h monitoring)
  ✅ No increase in error rates
  ✅ Documentation updated

NO-GO Triggers:
  ❌ AI accuracy <80% → More tuning needed
  ❌ Circuit breaker failures → Fix resilience
  ❌ Fallback broken → Fix before rollout
  ❌ AI Service uptime <95% → Stability issues
```

---

## 📖 DOCUMENTATION UPDATES

### Files to Update After AI Integration

#### 1. README.md
```markdown
## AI-Powered Features ✨

### Anomaly Detection
Analytics Service uses **machine learning** to detect anomalies with **85%+ accuracy**.

- Method: Isolation Forest + Z-score
- Confidence scores provided
- Real-time detection (<1s latency)
- Automatic fallback to rule-based if ML unavailable

### Predictions
**7-day forecasts** using time-series ML models:

- Models: Linear Regression, ARIMA, LSTM
- Accuracy: MAE <20%
- Updated daily
- Confidence intervals included

### Fallback Mechanism
If AI Service unavailable:
- Anomaly detection → simple threshold-based (60% accuracy)
- Predictions → 7-day average
- Seamless transition, no errors
```

#### 2. API_REFERENCE.md
```yaml
GET /api/v1/analytics/anomalies:
  Description: Get ML-detected anomalies
  Response:
    {
      "anomalies": [
        {
          "metric": "requests_total",
          "value": 1500,
          "threshold": 1000,
          "confidence": 0.92,
          "method": "ml_based",
          "severity": "warning"
        }
      ],
      "ai_ready": true
    }

GET /api/v1/analytics/predictions/{metric}:
  Description: Get 7-day ML predictions
  Response:
    {
      "predictions": [120, 125, 130, 128, 135, 140, 142],
      "dates": ["2025-10-07", ...],
      "confidence": 0.88,
      "mae": 0.15,
      "method": "linear_regression",
      "ai_ready": true
    }
```

#### 3. RUNBOOK.md
```markdown
## AI Service Troubleshooting

### Scenario: AI Service Down
Symptoms:
- `ai_ready: false` in API responses
- Fallback messages in logs
- Circuit breaker open

Actions:
1. Check AI Service health: `curl http://ai-service:8007/health`
2. Analytics will auto-fallback to stubs (60% accuracy)
3. Investigate AI Service logs
4. No impact to Analytics Service uptime

### Scenario: Low AI Accuracy
Symptoms:
- MAE >20%
- Anomaly F1-score <85%

Actions:
1. Check model version
2. Validate input data quality
3. Consider retraining models
4. Rollback to previous model version if needed
```

---

## 🔄 ROLLBACK PLAN

### If AI Integration Fails

#### Immediate Rollback (< 5 minutes)
```yaml
Action: Disable AI via feature flag

Steps:
  1. Set feature_flags.ai_enabled = false
  2. Restart Analytics Service (graceful)
  3. Verify stubs working
  4. Monitor for 30 minutes

Impact:
  - Back to rule-based anomalies (60% accuracy)
  - Back to average-based predictions
  - No data loss
  - No downtime
```

#### Full Rollback (< 30 minutes)
```yaml
Action: Revert to previous deployment

Steps:
  1. git revert {ai_integration_commit}
  2. Build new Docker image
  3. Deploy to production
  4. Verify stubs working
  5. Remove AI Service from dependencies

Impact:
  - Back to Sprint 16-18 state
  - Stubs only
  - No AI features
  - Zero downtime (blue-green deployment)
```

---

## 📅 TENTATIVE TIMELINE

```
Preconditions:
  - AI Service development: 4-6 weeks (separate team)
  - Analytics Service in production: Sprint 16-18 (Week 10)

AI Integration Sprint:
  Week 0: Pre-work
    - [ ] AI Service deployed to staging
    - [ ] Endpoints validated
    - [ ] Historical data prepared

  Week 1: Integration (8h)
    - [ ] Real AI client implemented
    - [ ] Circuit breaker + resilience
    - [ ] Integration tests

  Week 2: Anomaly Detection (8h)
    - [ ] ML anomaly detector
    - [ ] A/B testing framework
    - [ ] Validation (85%+ accuracy)

  Week 3: Predictions & Deploy (8h)
    - [ ] ML predictor
    - [ ] Model versioning
    - [ ] Production deployment (10% → 100%)

  Week 4: Monitoring & Tuning
    - Monitor accuracy
    - Tune models
    - Full rollout to 100%
```

---

## ✅ DELIVERABLES

### Code Deliverables
- ✅ AIServiceClient (real implementation)
- ✅ AnomalyDetectorML (85%+ accuracy)
- ✅ PredictorML (MAE <20%)
- ✅ Circuit breaker + retry logic
- ✅ Feature flags system
- ✅ A/B testing framework
- ✅ Integration tests (80%+ coverage)

### Documentation Deliverables
- ✅ Updated README (AI features)
- ✅ Updated API_REFERENCE (AI endpoints)
- ✅ Updated RUNBOOK (AI troubleshooting)
- ✅ ARCHITECTURE.md (AI integration diagram)
- ✅ AI model documentation (versioning, accuracy)

### Operational Deliverables
- ✅ Monitoring dashboard (AI metrics)
- ✅ Alerts for AI failures
- ✅ Runbook for AI incidents
- ✅ Rollback procedures tested

---

## 🎓 LESSONS LEARNED

### What Worked Well (Sprint 16-18)
✅ **Stub-first approach** - Decoupled from AI Service dependency
✅ **Clear fallbacks** - System works without AI
✅ **Gradual rollout planned** - Low risk integration
✅ **Feature flags** - Easy enable/disable

### What to Avoid
❌ **Blocking on AI** - Don't wait for AI to ship Analytics
❌ **Big bang integration** - Use gradual rollout instead
❌ **No fallbacks** - Always have plan B
❌ **Unrealistic targets** - 95% accuracy in 8h is fantasy

---

**Version**: 1.0
**Status**: 📋 PLANNED - Waiting for AI Service
**Last Updated**: 6 октября 2025
**Next Review**: After AI Service deployment
**Owner**: Analytics Team + AI Team
