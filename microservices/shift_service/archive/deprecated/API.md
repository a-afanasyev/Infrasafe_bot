# 📡 Shift Service - API Documentation

## 🌐 Base URL

```
Development: http://localhost:8007
Production: https://api.ukbot.com/shift-service
```

**Version**: v1
**Base Path**: `/api/v1`

---

## 🔐 Authentication

All endpoints require authentication via JWT token:

```http
Authorization: Bearer <jwt_token>
```

Service-to-service authentication:
```http
X-Service-Name: request-service
X-Service-API-Key: <service_api_key>
```

---

## 📚 API Endpoints Overview

**Total Endpoints**: 59
**Coverage**: 100% ✅

### Shifts API (11 endpoints)
- `GET /shifts/` - List shifts
- `POST /shifts/` - Create shift
- `GET /shifts/{shift_id}` - Get shift
- `PUT /shifts/{shift_id}` - Update shift
- `DELETE /shifts/{shift_id}` - Delete shift
- `POST /shifts/{shift_id}/assign` - Assign executor
- `POST /shifts/{shift_id}/unassign` - Unassign executor
- `POST /shifts/{shift_id}/complete` - Complete shift
- `GET /shifts/upcoming` - Get upcoming shifts
- `GET /shifts/unassigned` - Get unassigned shifts
- `GET /shifts/executor/{executor_id}` - Get executor shifts

### Templates API (6 endpoints)
- `GET /templates/` - List templates
- `POST /templates/` - Create template
- `GET /templates/{template_id}` - Get template
- `PUT /templates/{template_id}` - Update template
- `DELETE /templates/{template_id}` - Delete template
- `POST /templates/{template_id}/generate` - Generate shifts from template

### Analytics API (7 endpoints)
- `GET /analytics/shift-metrics` - Get shift performance metrics
- `GET /analytics/executor-performance/{executor_id}` - Get executor performance
- `GET /analytics/shift-trends` - Get shift trends
- `GET /analytics/predict-workload` - Predict future workload
- `GET /analytics/utilization` - Get utilization metrics
- `GET /analytics/status-distribution` - Get status distribution
- `GET /analytics/team-performance` - Get team performance

### Assignments API (8 endpoints)
- `GET /assignments/` - List assignments
- `POST /assignments/` - Create assignment
- `GET /assignments/{assignment_id}` - Get assignment
- `POST /assignments/{shift_id}/assign` - Assign shift (convenience)
- `POST /assignments/{shift_id}/unassign` - Unassign shift (convenience)
- `GET /assignments/shift/{shift_id}` - Get shift assignments
- `GET /assignments/executor/{executor_id}` - Get executor assignments
- `GET /assignments/recommendations` - Get AI recommendations

### Transfers API (8 endpoints)
- `GET /transfers/` - List transfers
- `POST /transfers/` - Create transfer request
- `GET /transfers/{transfer_id}` - Get transfer
- `POST /transfers/{transfer_id}/approve` - Approve transfer
- `POST /transfers/{transfer_id}/reject` - Reject transfer
- `POST /transfers/{transfer_id}/cancel` - Cancel transfer
- `GET /transfers/shift/{shift_id}/history` - Get shift transfer history
- `GET /transfers/suggestions/{transfer_id}` - Get replacement suggestions

### Schedule API (7 endpoints)
- `POST /schedule/conflicts/check` - Check schedule conflicts
- `GET /schedule/executor/{executor_id}/workload` - Get executor workload
- `GET /schedule/team/workload` - Get team workload distribution
- `GET /schedule/coverage/gaps` - Find coverage gaps
- `GET /schedule/balancing/recommendations` - Get balancing recommendations
- `GET /schedule/weekly/validate` - Validate weekly schedule
- `POST /schedule/conflicts/check-specialization` - Check specialization conflicts

### Internal API (12 endpoints)
- `GET /internal/health` - Health check
- `GET /internal/scheduler/status` - Get scheduler status
- `POST /internal/scheduler/trigger/{job_id}` - Trigger scheduled job
- `POST /internal/ai/assignment-recommendations` - Get AI recommendations
- `POST /internal/ai/optimize-schedule` - Optimize schedule with AI
- `POST /internal/ai/predict-demand` - Predict shift demand
- `GET /internal/ai/health` - AI service health check
- `GET /internal/stats` - Service statistics
- `POST /internal/cache/clear` - Clear cache
- `POST /internal/generate-service-token` - Generate service token
- `POST /internal/validate-service-credentials` - Validate service credentials
- `GET /internal/metrics` - Prometheus metrics

---

## 📖 Detailed Endpoint Documentation

### Shifts API

#### `POST /api/v1/shifts/` - Create Shift

Creates a new shift in the system.

**Request**:
```json
{
  "title": "Electrical Maintenance",
  "description": "Check and repair electrical systems",
  "specialization": "electrician",
  "shift_type": "scheduled",
  "start_time": "2025-10-15T08:00:00Z",
  "end_time": "2025-10-15T16:00:00Z",
  "location": "Building A, Floor 3",
  "coordinates": {
    "latitude": 55.7558,
    "longitude": 37.6173
  },
  "priority": 3,
  "executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "requirements": {
    "tools": ["multimeter", "screwdriver_set"],
    "certifications": ["electrical_license"]
  },
  "metadata": {
    "request_id": "REQ-2025-001",
    "building_access_code": "1234"
  }
}
```

**Response** (201 Created):
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "title": "Electrical Maintenance",
  "description": "Check and repair electrical systems",
  "specialization": "electrician",
  "shift_type": "scheduled",
  "status": "planned",
  "start_time": "2025-10-15T08:00:00Z",
  "end_time": "2025-10-15T16:00:00Z",
  "duration_hours": 8.0,
  "location": "Building A, Floor 3",
  "coordinates": {
    "latitude": 55.7558,
    "longitude": 37.6173
  },
  "priority": 3,
  "executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-10-03T10:00:00Z",
  "updated_at": "2025-10-03T10:00:00Z",
  "created_by": "admin-user-id"
}
```

**Errors**:
- `400 Bad Request` - Invalid data
- `401 Unauthorized` - Missing or invalid authentication
- `422 Unprocessable Entity` - Validation error

---

#### `GET /api/v1/shifts/` - List Shifts

Retrieves list of shifts with optional filters.

**Query Parameters**:
- `status` (string, optional): Filter by status (planned, active, completed, cancelled)
- `specialization` (string, optional): Filter by specialization
- `executor_id` (UUID, optional): Filter by executor
- `start_date` (datetime, optional): Filter shifts starting after this date
- `end_date` (datetime, optional): Filter shifts starting before this date
- `priority` (int, optional): Filter by priority (1-4)
- `skip` (int, optional): Pagination offset (default: 0)
- `limit` (int, optional): Page size (default: 50, max: 100)

**Request**:
```http
GET /api/v1/shifts/?status=planned&specialization=electrician&limit=20
```

**Response** (200 OK):
```json
{
  "items": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "title": "Electrical Maintenance",
      "specialization": "electrician",
      "status": "planned",
      "start_time": "2025-10-15T08:00:00Z",
      "end_time": "2025-10-15T16:00:00Z",
      "priority": 3,
      "executor_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

---

#### `POST /api/v1/shifts/{shift_id}/assign` - Assign Executor

Assigns an executor to a shift.

**Request**:
```json
{
  "executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "assigned_by": "manager-user-id",
  "assignment_method": "manual",
  "notes": "Best available electrician"
}
```

**Response** (200 OK):
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "planned",
  "assignment": {
    "id": "assignment-id",
    "assigned_at": "2025-10-03T10:05:00Z",
    "assigned_by": "manager-user-id",
    "assignment_method": "manual"
  }
}
```

---

### Analytics API

#### `GET /api/v1/analytics/shift-metrics` - Get Shift Metrics

Calculates comprehensive shift performance metrics.

**Query Parameters**:
- `start_date` (datetime, required): Start of analysis period
- `end_date` (datetime, required): End of analysis period
- `specialization` (string, optional): Filter by specialization

**Request**:
```http
GET /api/v1/analytics/shift-metrics?start_date=2025-09-01&end_date=2025-09-30&specialization=electrician
```

**Response** (200 OK):
```json
{
  "period": {
    "start_date": "2025-09-01T00:00:00Z",
    "end_date": "2025-09-30T23:59:59Z",
    "specialization": "electrician"
  },
  "overview": {
    "total_shifts": 120,
    "completed_shifts": 105,
    "cancelled_shifts": 10,
    "transferred_shifts": 5,
    "completion_rate": 87.5,
    "cancellation_rate": 8.3,
    "transfer_rate": 4.2
  },
  "duration": {
    "avg_duration_hours": 7.8,
    "median_duration_hours": 8.0,
    "total_work_hours": 819.0
  },
  "quality": {
    "avg_rating": 4.6,
    "avg_efficiency_score": 0.89,
    "shifts_with_rating": 98
  },
  "status_distribution": {
    "planned": 15,
    "active": 5,
    "completed": 105,
    "cancelled": 10
  },
  "type_distribution": {
    "scheduled": 95,
    "emergency": 20,
    "maintenance": 5
  }
}
```

---

#### `GET /api/v1/analytics/predict-workload` - Predict Workload

Predicts future shift demand using historical data and ML models.

**Query Parameters**:
- `target_date` (date, required): Date to predict for
- `specialization` (string, optional): Specific specialization
- `confidence_level` (float, optional): Confidence level (0.0-1.0, default: 0.8)

**Request**:
```http
GET /api/v1/analytics/predict-workload?target_date=2025-10-20&specialization=plumber
```

**Response** (200 OK):
```json
{
  "target_date": "2025-10-20",
  "specialization": "plumber",
  "prediction": {
    "predicted_shifts": 12,
    "predicted_hours": 96,
    "confidence": 0.85,
    "model": "time_series_lstm"
  },
  "breakdown": {
    "morning": 4,
    "afternoon": 5,
    "evening": 3
  },
  "recommendations": [
    "Schedule 2 additional plumbers",
    "Prepare emergency on-call list",
    "Stock maintenance supplies"
  ],
  "historical_comparison": {
    "same_weekday_avg": 10,
    "same_month_avg": 11,
    "overall_avg": 9
  }
}
```

---

### Transfers API

#### `POST /api/v1/transfers/` - Create Transfer Request

Creates a shift transfer request.

**Request**:
```json
{
  "shift_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "from_executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "to_executor_id": null,
  "transfer_type": "voluntary",
  "reason": "Personal emergency - need replacement",
  "auto_assign_criteria": {
    "same_specialization": true,
    "min_rating": 4.0,
    "max_distance_km": 10
  },
  "notes": "Urgent - shift starts in 24 hours"
}
```

**Response** (201 Created):
```json
{
  "id": "transfer-id",
  "shift_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "from_executor_id": "550e8400-e29b-41d4-a716-446655440000",
  "to_executor_id": null,
  "status": "pending",
  "transfer_type": "voluntary",
  "reason": "Personal emergency - need replacement",
  "assignment_deadline": "2025-10-05T08:00:00Z",
  "requested_at": "2025-10-03T10:00:00Z",
  "requested_by": "executor-user-id"
}
```

---

#### `GET /api/v1/transfers/suggestions/{transfer_id}` - Get Replacement Suggestions

Gets AI-powered suggestions for replacement executors.

**Response** (200 OK):
```json
{
  "transfer_id": "transfer-id",
  "shift": {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "specialization": "electrician",
    "start_time": "2025-10-05T08:00:00Z",
    "location": "Building A, Floor 3"
  },
  "suggestions": [
    {
      "executor_id": "executor-1-id",
      "name": "John Smith",
      "specializations": ["electrician", "plumber"],
      "rating": 4.8,
      "distance_km": 2.5,
      "availability_score": 0.95,
      "confidence": 0.92,
      "reason": "Perfect match: same specialization, high rating, nearby",
      "estimated_travel_time_minutes": 15
    },
    {
      "executor_id": "executor-2-id",
      "name": "Jane Doe",
      "specializations": ["electrician"],
      "rating": 4.6,
      "distance_km": 5.0,
      "availability_score": 0.88,
      "confidence": 0.85,
      "reason": "Good match: specialized electrician, available",
      "estimated_travel_time_minutes": 25
    }
  ],
  "total_suggestions": 2
}
```

---

### Internal API

#### `GET /api/v1/internal/health` - Health Check

Service health check endpoint.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "shift-service",
  "version": "1.0.0",
  "timestamp": "2025-10-03T10:00:00Z",
  "components": {
    "database": {
      "status": "up",
      "latency_ms": 5
    },
    "redis": {
      "status": "up",
      "latency_ms": 2
    },
    "ai_service": {
      "status": "fallback",
      "mode": "enhanced"
    },
    "scheduler": {
      "status": "running",
      "active_jobs": 9
    }
  },
  "metrics": {
    "total_shifts": 1523,
    "active_shifts": 45,
    "scheduled_shifts": 234
  }
}
```

---

## 🔄 Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 204 | No Content | Request successful, no content returned |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 422 | Unprocessable Entity | Validation error |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service temporarily unavailable |

---

## 📊 Rate Limiting

**Default Limits**:
- **Anonymous**: 100 requests/hour
- **Authenticated**: 1000 requests/hour
- **Service-to-Service**: 10000 requests/hour

**Headers**:
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1696334400
```

---

## 🎯 Pagination

All list endpoints support pagination:

**Request**:
```http
GET /api/v1/shifts/?skip=20&limit=10
```

**Response**:
```json
{
  "items": [...],
  "total": 150,
  "skip": 20,
  "limit": 10,
  "has_more": true
}
```

---

## 🔍 Filtering & Sorting

### Filtering

```http
GET /api/v1/shifts/?status=planned&specialization=electrician&priority=3
```

### Sorting

```http
GET /api/v1/shifts/?sort_by=start_time&order=desc
```

---

## 📝 Webhooks

Shift Service can send webhooks for events:

**Events**:
- `shift.created`
- `shift.assigned`
- `shift.completed`
- `shift.cancelled`
- `transfer.requested`
- `transfer.approved`

**Payload Example**:
```json
{
  "event": "shift.assigned",
  "timestamp": "2025-10-03T10:00:00Z",
  "data": {
    "shift_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "executor_id": "550e8400-e29b-41d4-a716-446655440000",
    "assigned_by": "manager-user-id"
  }
}
```

---

## 🧪 Testing Endpoints

**Postman Collection**: Available at `/docs/postman/shift-service.json`

**Swagger UI**: http://localhost:8007/docs

**ReDoc**: http://localhost:8007/redoc

---

## 📚 Additional Resources

- **OpenAPI Spec**: http://localhost:8007/openapi.json
- **Service Documentation**: `SHIFT_SERVICE_DOCUMENTATION.md`
- **Testing Guide**: `TESTING.md`
- **README**: `README.md`

---

**Last Updated**: 2025-10-03
**API Version**: v1
**Endpoints**: 59
**Coverage**: 100% ✅
