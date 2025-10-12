# 🌐 Shift Service API Reference
**UK Management Bot - Complete API Documentation**
**Version**: 1.0.0
**Base URL**: `http://localhost:8007/api/v1`

## 📋 Table of Contents
1. [Authentication](#authentication)
2. [Error Handling](#error-handling)
3. [Pagination](#pagination)
4. [Shift Management](#shift-management)
5. [Assignment Management](#assignment-management)
6. [Transfer Management](#transfer-management)
7. [Template Management](#template-management)
8. [Analytics API](#analytics-api)
9. [Internal API](#internal-api)
10. [WebSocket Events](#websocket-events)

---

## 🔐 Authentication

### Service Authentication
All API endpoints require service authentication using the `X-Service-API-Key` header.

```bash
X-Service-API-Key: shift-service-api-key-change-in-production
```

### User Authentication (Future)
For user-facing endpoints, JWT tokens will be required:

```bash
Authorization: Bearer <jwt_token>
```

---

## ❌ Error Handling

### Error Response Format
```json
{
  "error": {
    "code": "SHIFT_NOT_FOUND",
    "message": "Shift with ID '12345' not found",
    "details": {
      "shift_id": "12345",
      "timestamp": "2025-09-30T11:00:00Z"
    }
  }
}
```

### HTTP Status Codes

| Code | Status | Description |
|------|--------|-------------|
| `200` | OK | Request successful |
| `201` | Created | Resource created successfully |
| `400` | Bad Request | Invalid request parameters |
| `401` | Unauthorized | Authentication required |
| `403` | Forbidden | Insufficient permissions |
| `404` | Not Found | Resource not found |
| `409` | Conflict | Resource conflict |
| `422` | Unprocessable Entity | Validation error |
| `500` | Internal Server Error | Server error |
| `503` | Service Unavailable | Service temporarily unavailable |

### Error Codes

| Code | Description |
|------|-------------|
| `SHIFT_NOT_FOUND` | Shift does not exist |
| `SHIFT_ALREADY_ASSIGNED` | Shift already has an executor |
| `EXECUTOR_NOT_AVAILABLE` | Executor is not available for assignment |
| `INVALID_TIME_RANGE` | Invalid start/end time combination |
| `TRANSFER_NOT_ALLOWED` | Transfer request not permitted |
| `TEMPLATE_VALIDATION_ERROR` | Template validation failed |
| `SCHEDULING_CONFLICT` | Schedule conflict detected |
| `AI_SERVICE_UNAVAILABLE` | AI service temporarily unavailable |

---

## 📄 Pagination

### Request Parameters
```bash
GET /api/v1/shifts?page=1&size=20&sort=start_time&order=desc
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (1-based) |
| `size` | integer | 20 | Items per page (max 100) |
| `sort` | string | id | Sort field |
| `order` | string | asc | Sort order (asc/desc) |

### Response Format
```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "size": 20,
    "total": 150,
    "pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## 📅 Shift Management

### GET `/shifts`
Retrieve shifts with filtering and pagination.

#### Query Parameters
| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `status` | string | Filter by status | `planned,active` |
| `executor_id` | UUID | Filter by executor | `123e4567-e89b-12d3-a456-426614174000` |
| `specialization` | string | Filter by specialization | `plumbing,electrical` |
| `start_date` | date | Filter by start date | `2025-10-01` |
| `end_date` | date | Filter by end date | `2025-10-31` |
| `location` | string | Search in location | `Building A` |
| `priority_min` | integer | Minimum priority | `2` |
| `priority_max` | integer | Maximum priority | `5` |

#### Response
```json
{
  "shifts": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "title": "Emergency Plumbing Repair",
      "specialization": "plumbing",
      "status": "planned",
      "start_time": "2025-10-01T09:00:00Z",
      "end_time": "2025-10-01T17:00:00Z",
      "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
      "location": "Building A, Floor 2, Room 201",
      "coordinates": {
        "lat": 55.7558,
        "lon": 37.6176
      },
      "priority": 4,
      "requirements": ["plumbing_tools", "emergency_kit"],
      "template_id": "456e7890-e89b-12d3-a456-426614174000",
      "completion_rating": null,
      "efficiency_score": null,
      "created_at": "2025-09-30T10:00:00Z",
      "updated_at": "2025-09-30T10:00:00Z",
      "metadata": {
        "estimated_duration": 8.0,
        "complexity": "medium",
        "customer_priority": true
      }
    }
  ],
  "pagination": {
    "page": 1,
    "size": 20,
    "total": 45,
    "pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

### POST `/shifts`
Create a new shift.

#### Request Body
```json
{
  "title": "HVAC Maintenance Check",
  "specialization": "hvac",
  "start_time": "2025-10-02T08:00:00Z",
  "end_time": "2025-10-02T16:00:00Z",
  "location": "Building C, Rooftop",
  "coordinates": {
    "lat": 55.7500,
    "lon": 37.6200
  },
  "priority": 2,
  "requirements": ["hvac_tools", "safety_harness", "ladder"],
  "template_id": "456e7890-e89b-12d3-a456-426614174000",
  "auto_assign": true,
  "notes": "Quarterly maintenance check",
  "metadata": {
    "estimated_duration": 8.0,
    "complexity": "low",
    "recurring": true
  }
}
```

#### Validation Rules
- `title`: Required, 3-200 characters
- `specialization`: Must be valid enum value
- `start_time`: Must be in future
- `end_time`: Must be after start_time
- `location`: Required, max 500 characters
- `priority`: Integer 1-5
- `coordinates`: Optional, valid lat/lon

#### Response
```json
{
  "id": "789e0123-e89b-12d3-a456-426614174000",
  "status": "created",
  "message": "Shift created successfully",
  "auto_assignment": {
    "attempted": true,
    "success": true,
    "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
    "confidence": 0.85
  }
}
```

### GET `/shifts/{shift_id}`
Retrieve specific shift with full details.

#### Response
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "title": "Emergency Plumbing Repair",
  "specialization": "plumbing",
  "status": "active",
  "start_time": "2025-10-01T09:00:00Z",
  "end_time": "2025-10-01T17:00:00Z",
  "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
  "location": "Building A, Floor 2, Room 201",
  "coordinates": {
    "lat": 55.7558,
    "lon": 37.6176
  },
  "priority": 4,
  "requirements": ["plumbing_tools", "emergency_kit"],
  "template_id": "456e7890-e89b-12d3-a456-426614174000",
  "completion_rating": null,
  "efficiency_score": null,
  "created_at": "2025-09-30T10:00:00Z",
  "updated_at": "2025-10-01T09:30:00Z",
  "assignments": [
    {
      "id": "assignment-uuid",
      "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
      "assigned_by": "manager-uuid",
      "assigned_at": "2025-09-30T15:00:00Z",
      "assignment_method": "ai_optimization",
      "confidence_score": 0.89,
      "is_active": true,
      "notes": "Best match for specialization and location"
    }
  ],
  "transfers": [
    {
      "id": "transfer-uuid",
      "from_executor_id": "old-executor-uuid",
      "to_executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
      "requested_by": "old-executor-uuid",
      "requested_at": "2025-09-30T14:00:00Z",
      "approved_by": "manager-uuid",
      "approved_at": "2025-09-30T14:30:00Z",
      "status": "approved",
      "reason": "Schedule conflict resolved",
      "urgency": "medium"
    }
  ],
  "comments": [
    {
      "id": "comment-uuid",
      "author_id": "user-uuid",
      "content": "Customer reported water leak in ceiling",
      "created_at": "2025-09-30T10:15:00Z"
    }
  ]
}
```

### PUT `/shifts/{shift_id}`
Update shift details.

#### Request Body
```json
{
  "title": "Updated Emergency Plumbing Repair",
  "priority": 5,
  "requirements": ["plumbing_tools", "emergency_kit", "pipe_replacement"],
  "notes": "Updated requirements after inspection"
}
```

#### Response
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "updated",
  "message": "Shift updated successfully",
  "changes": ["title", "priority", "requirements"]
}
```

### DELETE `/shifts/{shift_id}`
Soft delete a shift.

#### Response
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "deleted",
  "message": "Shift deleted successfully"
}
```

---

## 👷 Assignment Management

### POST `/shifts/{shift_id}/assign`
Assign executor to shift.

#### Request Body
```json
{
  "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
  "assignment_method": "manual",
  "notes": "Requested by executor, has experience with this location",
  "override_conflicts": false
}
```

#### Response
```json
{
  "assignment_id": "assignment-uuid",
  "status": "assigned",
  "message": "Executor assigned successfully",
  "conflicts_detected": [],
  "confidence_score": 0.95
}
```

### GET `/shifts/{shift_id}/recommendations`
Get AI-powered executor recommendations.

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max recommendations (default: 5) |
| `include_busy` | boolean | Include busy executors (default: false) |

#### Response
```json
{
  "recommendations": [
    {
      "executor_id": "987fcdeb-51d3-45a7-b123-456789abcdef",
      "score": 0.92,
      "confidence": 0.88,
      "reasons": [
        "Perfect specialization match",
        "Optimal location proximity",
        "High performance rating"
      ],
      "factors": {
        "specialization_match": 1.0,
        "location_score": 0.95,
        "availability_score": 0.9,
        "performance_rating": 0.92,
        "workload_balance": 0.85
      },
      "estimated_travel_time": 15,
      "current_workload": 0.6
    }
  ],
  "fallback_used": false,
  "ai_service_available": true
}
```

### DELETE `/shifts/{shift_id}/assign`
Unassign executor from shift.

#### Response
```json
{
  "status": "unassigned",
  "message": "Executor unassigned successfully",
  "reassignment_recommended": true
}
```

### GET `/assignments`
Get assignment history with filtering.

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `executor_id` | UUID | Filter by executor |
| `shift_id` | UUID | Filter by shift |
| `method` | string | Filter by assignment method |
| `active_only` | boolean | Show only active assignments |

---

## 🔄 Transfer Management

### POST `/shifts/{shift_id}/transfer`
Request shift transfer.

#### Request Body
```json
{
  "to_executor_id": "new-executor-uuid",
  "reason": "Schedule conflict - family emergency",
  "urgency": "high",
  "notes": "Need immediate replacement for tomorrow's shift",
  "auto_approve": false
}
```

#### Response
```json
{
  "transfer_id": "transfer-uuid",
  "status": "pending",
  "message": "Transfer request submitted",
  "requires_approval": true,
  "estimated_approval_time": "2-4 hours"
}
```

### GET `/transfers`
Get transfer requests with filtering.

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `executor_id` | UUID | Filter by executor |
| `urgency` | string | Filter by urgency |
| `pending_only` | boolean | Show only pending transfers |

#### Response
```json
{
  "transfers": [
    {
      "id": "transfer-uuid",
      "shift_id": "shift-uuid",
      "from_executor_id": "old-executor-uuid",
      "to_executor_id": "new-executor-uuid",
      "requested_by": "old-executor-uuid",
      "requested_at": "2025-09-30T14:00:00Z",
      "status": "pending",
      "reason": "Schedule conflict - family emergency",
      "urgency": "high",
      "admin_notes": null,
      "auto_approval_eligible": false
    }
  ],
  "pagination": {...}
}
```

### PUT `/transfers/{transfer_id}/approve`
Approve transfer request.

#### Request Body
```json
{
  "admin_notes": "Approved due to emergency circumstances",
  "effective_immediately": true
}
```

#### Response
```json
{
  "transfer_id": "transfer-uuid",
  "status": "approved",
  "message": "Transfer approved successfully",
  "effective_at": "2025-09-30T15:00:00Z"
}
```

### PUT `/transfers/{transfer_id}/reject`
Reject transfer request.

#### Request Body
```json
{
  "admin_notes": "Insufficient notice, please find alternative solution",
  "suggest_alternatives": true
}
```

#### Response
```json
{
  "transfer_id": "transfer-uuid",
  "status": "rejected",
  "message": "Transfer rejected",
  "alternatives": [
    {
      "suggestion": "Swap with another executor",
      "available_swaps": 3
    }
  ]
}
```

---

## 📋 Template Management

### GET `/templates`
Retrieve shift templates.

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `specialization` | string | Filter by specialization |
| `active_only` | boolean | Show only active templates |
| `schedule_pattern` | string | Filter by schedule pattern |

#### Response
```json
{
  "templates": [
    {
      "id": "template-uuid",
      "name": "Standard Plumbing Maintenance",
      "specialization": "plumbing",
      "duration_hours": 8,
      "default_priority": 2,
      "requirements": ["plumbing_tools", "pipe_materials"],
      "schedule_pattern": "weekly",
      "days_of_week": [1, 3, 5],
      "start_time": "09:00:00",
      "location_template": "Building {building}, Floor {floor}",
      "auto_assign": true,
      "is_active": true,
      "created_at": "2025-09-01T10:00:00Z",
      "usage_count": 45
    }
  ],
  "pagination": {...}
}
```

### POST `/templates`
Create new shift template.

#### Request Body
```json
{
  "name": "Emergency Electrical Response",
  "specialization": "electrical",
  "duration_hours": 4,
  "default_priority": 4,
  "requirements": ["electrical_tools", "safety_equipment", "testing_devices"],
  "schedule_pattern": "on_demand",
  "auto_assign": true,
  "location_template": "Emergency location: {address}",
  "description": "Template for emergency electrical repairs"
}
```

#### Response
```json
{
  "id": "new-template-uuid",
  "status": "created",
  "message": "Template created successfully"
}
```

### PUT `/templates/{template_id}`
Update template.

### DELETE `/templates/{template_id}`
Deactivate template.

---

## 📊 Analytics API

### GET `/analytics/summary`
Get comprehensive analytics summary.

#### Query Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | Time period (day/week/month/year) |
| `start_date` | date | Custom start date |
| `end_date` | date | Custom end date |
| `specialization` | string | Filter by specialization |

#### Response
```json
{
  "period": {
    "type": "last_30_days",
    "start_date": "2025-09-01",
    "end_date": "2025-09-30"
  },
  "summary": {
    "total_shifts": 320,
    "completed_shifts": 298,
    "cancelled_shifts": 12,
    "success_rate": 93.13,
    "average_duration": 7.2,
    "total_hours": 2304
  },
  "specialization_breakdown": {
    "plumbing": {"count": 89, "success_rate": 95.5},
    "electrical": {"count": 76, "success_rate": 92.1},
    "maintenance": {"count": 68, "success_rate": 94.1},
    "cleaning": {"count": 45, "success_rate": 97.8},
    "other": {"count": 42, "success_rate": 88.1}
  },
  "efficiency_metrics": {
    "assignment_speed": {
      "average_minutes": 18.5,
      "ai_assisted": 12.3,
      "manual": 28.7
    },
    "transfer_rate": 8.2,
    "optimization_score": 0.87,
    "ai_fallback_usage": 15.3
  },
  "trends": {
    "shift_volume": [
      {"date": "2025-09-01", "count": 12},
      {"date": "2025-09-02", "count": 15}
    ],
    "success_rate": [
      {"date": "2025-09-01", "rate": 92.3},
      {"date": "2025-09-02", "rate": 94.1}
    ]
  }
}
```

### GET `/analytics/performance`
Get performance metrics.

#### Response
```json
{
  "executor_performance": {
    "top_performers": [
      {
        "executor_id": "exec-uuid-1",
        "shifts_completed": 45,
        "success_rate": 97.8,
        "average_rating": 4.8,
        "efficiency_score": 0.92
      }
    ],
    "performance_distribution": {
      "excellent": 45,
      "good": 78,
      "average": 23,
      "below_average": 8
    }
  },
  "operational_metrics": {
    "average_response_time": "4.2 hours",
    "first_time_fix_rate": 87.3,
    "customer_satisfaction": 4.6,
    "resource_utilization": 0.76
  }
}
```

### GET `/analytics/optimization`
Get optimization statistics.

#### Response
```json
{
  "ai_optimization": {
    "optimization_attempts": 1247,
    "successful_optimizations": 1089,
    "success_rate": 87.3,
    "average_improvement": 18.7,
    "fallback_usage": {
      "total_calls": 456,
      "fallback_calls": 127,
      "fallback_rate": 27.9
    }
  },
  "automation_impact": {
    "manual_assignments": 234,
    "ai_assignments": 892,
    "automation_rate": 79.2,
    "time_saved_hours": 156.8
  }
}
```

---

## 🔧 Internal API

### Health & Diagnostics

#### GET `/internal/health`
Comprehensive service health check.

#### GET `/internal/info`
Service information and metadata.

#### GET `/internal/metrics`
Prometheus metrics for monitoring.

### Background Task Management

#### GET `/internal/scheduler/status`
Background scheduler detailed status.

#### POST `/internal/scheduler/trigger/{job_id}`
Manually trigger specific background job.

#### POST `/internal/scheduler/pause/{job_id}`
Pause background job execution.

#### POST `/internal/scheduler/resume/{job_id}`
Resume paused background job.

### AI Integration Management

#### GET `/internal/ai/health`
AI service integration health status.

#### GET `/internal/ai/fallback/status`
AI fallback system configuration and status.

#### POST `/internal/ai/fallback/test`
Test all AI fallback modes with sample data.

#### POST `/internal/ai/test/integration`
Comprehensive AI integration testing.

### Data Management

#### GET `/internal/migration/status`
Data migration status and statistics.

#### POST `/internal/migration/validate`
Validate migration data integrity.

#### GET `/internal/database/stats`
Database performance statistics.

---

## 🔌 WebSocket Events

### Connection
```javascript
const ws = new WebSocket('ws://localhost:8007/ws/shifts');
```

### Event Types

#### `shift.created`
```json
{
  "event": "shift.created",
  "data": {
    "shift_id": "shift-uuid",
    "title": "New Emergency Repair",
    "specialization": "plumbing",
    "priority": 4,
    "created_at": "2025-09-30T15:00:00Z"
  }
}
```

#### `shift.assigned`
```json
{
  "event": "shift.assigned",
  "data": {
    "shift_id": "shift-uuid",
    "executor_id": "executor-uuid",
    "assignment_method": "ai_optimization",
    "confidence": 0.89
  }
}
```

#### `shift.status_changed`
```json
{
  "event": "shift.status_changed",
  "data": {
    "shift_id": "shift-uuid",
    "old_status": "planned",
    "new_status": "active",
    "changed_at": "2025-09-30T15:30:00Z"
  }
}
```

#### `transfer.requested`
```json
{
  "event": "transfer.requested",
  "data": {
    "transfer_id": "transfer-uuid",
    "shift_id": "shift-uuid",
    "from_executor_id": "old-executor-uuid",
    "to_executor_id": "new-executor-uuid",
    "urgency": "high"
  }
}
```

### Subscription Management
```javascript
// Subscribe to specific shift updates
ws.send(JSON.stringify({
  "action": "subscribe",
  "channel": "shift",
  "shift_id": "shift-uuid"
}));

// Subscribe to executor updates
ws.send(JSON.stringify({
  "action": "subscribe",
  "channel": "executor",
  "executor_id": "executor-uuid"
}));

// Unsubscribe
ws.send(JSON.stringify({
  "action": "unsubscribe",
  "channel": "shift",
  "shift_id": "shift-uuid"
}));
```

---

## 📚 SDK Examples

### Python SDK
```python
import asyncio
from shift_service_client import ShiftServiceClient

async def main():
    client = ShiftServiceClient(
        base_url="http://localhost:8007",
        api_key="shift-service-api-key-change-in-production"
    )

    # Create shift
    shift = await client.shifts.create({
        "title": "Emergency Repair",
        "specialization": "plumbing",
        "start_time": "2025-10-01T09:00:00Z",
        "end_time": "2025-10-01T17:00:00Z",
        "location": "Building A",
        "priority": 4
    })

    # Get recommendations
    recommendations = await client.shifts.get_recommendations(shift.id)

    # Assign executor
    assignment = await client.shifts.assign(
        shift.id,
        executor_id=recommendations[0].executor_id
    )

    print(f"Shift {shift.id} assigned to {assignment.executor_id}")

asyncio.run(main())
```

### JavaScript SDK
```javascript
import { ShiftServiceClient } from '@uk-management/shift-service-client';

const client = new ShiftServiceClient({
  baseURL: 'http://localhost:8007',
  apiKey: 'shift-service-api-key-change-in-production'
});

async function createAndAssignShift() {
  // Create shift
  const shift = await client.shifts.create({
    title: 'HVAC Maintenance',
    specialization: 'hvac',
    startTime: '2025-10-01T08:00:00Z',
    endTime: '2025-10-01T16:00:00Z',
    location: 'Building C Rooftop',
    priority: 2
  });

  // Get AI recommendations
  const recommendations = await client.shifts.getRecommendations(shift.id);

  // Auto-assign best recommendation
  if (recommendations.length > 0) {
    const assignment = await client.shifts.assign(shift.id, {
      executorId: recommendations[0].executorId,
      assignmentMethod: 'ai_optimization'
    });

    console.log(`Shift assigned with confidence: ${assignment.confidence}`);
  }
}
```

---

**Last Updated**: 30 September 2025
**API Version**: 1.0.0
**Documentation Version**: 1.0.0