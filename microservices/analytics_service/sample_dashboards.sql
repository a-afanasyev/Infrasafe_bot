-- Sample Dashboards for Analytics Service
-- Sprint 16-18: Analytics Service
-- Date: October 6, 2025
--
-- This file contains pre-configured dashboards for quick setup
-- Run: psql -U analytics_user -d analytics_db -f sample_dashboards.sql

-- ============================================================
-- Dashboard 1: Shift Management Overview
-- ============================================================

INSERT INTO dashboards (
    name,
    slug,
    description,
    is_public,
    is_default,
    refresh_interval,
    layout
) VALUES (
    'Shift Management Overview',
    'shift-management-overview',
    'Comprehensive overview of shift performance, completion rates, and executor utilization',
    true,
    true,
    300,
    '{
        "grid_columns": 12,
        "row_height": 60,
        "widgets": [
            {
                "id": "widget-active-shifts",
                "type": "kpi_card",
                "position": {"x": 0, "y": 0, "w": 3, "h": 2},
                "config": {
                    "kpi_name": "active_shifts",
                    "granularity": "daily",
                    "show_trend": true,
                    "comparison_period": "previous"
                }
            },
            {
                "id": "widget-completion-rate",
                "type": "kpi_card",
                "position": {"x": 3, "y": 0, "w": 3, "h": 2},
                "config": {
                    "kpi_name": "shift_completion_rate",
                    "granularity": "daily",
                    "show_trend": true,
                    "comparison_period": "previous"
                }
            },
            {
                "id": "widget-executor-utilization",
                "type": "gauge_chart",
                "position": {"x": 6, "y": 0, "w": 3, "h": 2},
                "config": {
                    "kpi_name": "executor_utilization",
                    "granularity": "daily",
                    "thresholds": {
                        "critical": 50,
                        "warning": 75,
                        "good": 90
                    }
                }
            },
            {
                "id": "widget-avg-duration",
                "type": "kpi_card",
                "position": {"x": 9, "y": 0, "w": 3, "h": 2},
                "config": {
                    "kpi_name": "avg_shift_duration",
                    "granularity": "daily",
                    "show_trend": true
                }
            },
            {
                "id": "widget-shifts-trend",
                "type": "time_series_chart",
                "position": {"x": 0, "y": 2, "w": 12, "h": 4},
                "config": {
                    "kpis": ["active_shifts", "shift_completion_rate"],
                    "granularity": "daily",
                    "period_days": 30
                }
            },
            {
                "id": "widget-comparison-table",
                "type": "comparison_table",
                "position": {"x": 0, "y": 6, "w": 12, "h": 3},
                "config": {
                    "kpis": [
                        "active_shifts",
                        "shift_completion_rate",
                        "executor_utilization"
                    ],
                    "granularity": "daily",
                    "comparison_periods": ["today", "yesterday", "last_week"]
                }
            }
        ]
    }'::jsonb
);

-- ============================================================
-- Dashboard 2: Real-time Operations
-- ============================================================

INSERT INTO dashboards (
    name,
    slug,
    description,
    is_public,
    is_default,
    refresh_interval,
    layout
) VALUES (
    'Real-time Operations',
    'realtime-operations',
    'Live view of current operations with 5-second updates',
    true,
    true,
    5,
    '{
        "grid_columns": 12,
        "row_height": 60,
        "widgets": [
            {
                "id": "widget-realtime-shifts",
                "type": "realtime_metric",
                "position": {"x": 0, "y": 0, "w": 4, "h": 3},
                "config": {
                    "metric": "active_shifts"
                }
            },
            {
                "id": "widget-realtime-requests",
                "type": "realtime_metric",
                "position": {"x": 4, "y": 0, "w": 4, "h": 3},
                "config": {
                    "metric": "requests_in_progress"
                }
            },
            {
                "id": "widget-realtime-users",
                "type": "realtime_metric",
                "position": {"x": 8, "y": 0, "w": 4, "h": 3},
                "config": {
                    "metric": "active_users"
                }
            },
            {
                "id": "widget-shifts-trend-indicator",
                "type": "trend_indicator",
                "position": {"x": 0, "y": 3, "w": 6, "h": 2},
                "config": {
                    "kpi_name": "active_shifts",
                    "granularity": "daily",
                    "comparison_days": 7
                }
            },
            {
                "id": "widget-completion-trend",
                "type": "trend_indicator",
                "position": {"x": 6, "y": 3, "w": 6, "h": 2},
                "config": {
                    "kpi_name": "shift_completion_rate",
                    "granularity": "daily",
                    "comparison_days": 7
                }
            }
        ]
    }'::jsonb
);

-- ============================================================
-- Dashboard 3: Request Management
-- ============================================================

INSERT INTO dashboards (
    name,
    slug,
    description,
    is_public,
    is_default,
    refresh_interval,
    layout
) VALUES (
    'Request Management Dashboard',
    'request-management',
    'Detailed view of request processing and completion metrics',
    true,
    false,
    300,
    '{
        "grid_columns": 12,
        "row_height": 60,
        "widgets": [
            {
                "id": "widget-active-requests",
                "type": "kpi_card",
                "position": {"x": 0, "y": 0, "w": 4, "h": 2},
                "config": {
                    "kpi_name": "active_requests",
                    "granularity": "daily",
                    "show_trend": true
                }
            },
            {
                "id": "widget-request-completion",
                "type": "gauge_chart",
                "position": {"x": 4, "y": 0, "w": 4, "h": 2},
                "config": {
                    "kpi_name": "request_completion_rate",
                    "granularity": "daily",
                    "thresholds": {
                        "critical": 60,
                        "warning": 80,
                        "good": 95
                    }
                }
            },
            {
                "id": "widget-avg-response-time",
                "type": "kpi_card",
                "position": {"x": 8, "y": 0, "w": 4, "h": 2},
                "config": {
                    "kpi_name": "avg_request_response_time",
                    "granularity": "daily",
                    "show_trend": true
                }
            },
            {
                "id": "widget-requests-trend",
                "type": "time_series_chart",
                "position": {"x": 0, "y": 2, "w": 12, "h": 4},
                "config": {
                    "kpis": [
                        "active_requests",
                        "request_completion_rate",
                        "avg_request_response_time"
                    ],
                    "granularity": "daily",
                    "period_days": 30
                }
            }
        ]
    }'::jsonb
);

-- ============================================================
-- Dashboard 4: Executive Summary
-- ============================================================

INSERT INTO dashboards (
    name,
    slug,
    description,
    is_public,
    is_default,
    refresh_interval,
    layout
) VALUES (
    'Executive Summary',
    'executive-summary',
    'High-level overview of all key metrics for management',
    true,
    true,
    600,
    '{
        "grid_columns": 12,
        "row_height": 60,
        "widgets": [
            {
                "id": "widget-comparison-all-kpis",
                "type": "comparison_table",
                "position": {"x": 0, "y": 0, "w": 12, "h": 4},
                "config": {
                    "kpis": [
                        "active_shifts",
                        "shift_completion_rate",
                        "active_requests",
                        "request_completion_rate",
                        "executor_utilization",
                        "avg_shift_duration",
                        "avg_request_response_time"
                    ],
                    "granularity": "daily",
                    "comparison_periods": ["today", "yesterday", "last_week"]
                }
            },
            {
                "id": "widget-shifts-weekly-trend",
                "type": "time_series_chart",
                "position": {"x": 0, "y": 4, "w": 6, "h": 4},
                "config": {
                    "kpis": ["active_shifts", "shift_completion_rate"],
                    "granularity": "weekly",
                    "period_days": 90
                }
            },
            {
                "id": "widget-requests-weekly-trend",
                "type": "time_series_chart",
                "position": {"x": 6, "y": 4, "w": 6, "h": 4},
                "config": {
                    "kpis": ["active_requests", "request_completion_rate"],
                    "granularity": "weekly",
                    "period_days": 90
                }
            }
        ]
    }'::jsonb
);

-- ============================================================
-- Dashboard 5: Performance Monitoring
-- ============================================================

INSERT INTO dashboards (
    name,
    slug,
    description,
    owner_id,
    is_public,
    is_default,
    refresh_interval,
    layout
) VALUES (
    'Performance Monitoring',
    'performance-monitoring',
    'Technical dashboard for monitoring service performance and health',
    'admin',
    false,
    false,
    60,
    '{
        "grid_columns": 12,
        "row_height": 60,
        "widgets": [
            {
                "id": "widget-realtime-all",
                "type": "comparison_table",
                "position": {"x": 0, "y": 0, "w": 12, "h": 2},
                "config": {
                    "kpis": [
                        "active_shifts",
                        "active_requests",
                        "shift_completion_rate",
                        "request_completion_rate"
                    ],
                    "granularity": "daily",
                    "comparison_periods": ["today", "yesterday"]
                }
            },
            {
                "id": "widget-all-trends",
                "type": "time_series_chart",
                "position": {"x": 0, "y": 2, "w": 12, "h": 5},
                "config": {
                    "kpis": [
                        "active_shifts",
                        "shift_completion_rate",
                        "active_requests",
                        "request_completion_rate"
                    ],
                    "granularity": "daily",
                    "period_days": 14
                }
            }
        ]
    }'::jsonb
);

-- ============================================================
-- Verification Queries
-- ============================================================

-- Show all dashboards
SELECT
    id,
    name,
    slug,
    is_public,
    is_default,
    refresh_interval,
    jsonb_array_length(layout->'widgets') as widget_count,
    created_at
FROM dashboards
ORDER BY is_default DESC, created_at;

-- Show dashboard details
SELECT
    name,
    slug,
    description,
    is_default,
    jsonb_pretty(layout) as layout_json
FROM dashboards
WHERE slug = 'shift-management-overview';

-- Count widgets by type
SELECT
    d.name as dashboard_name,
    w.value->>'type' as widget_type,
    count(*) as count
FROM dashboards d,
     jsonb_array_elements(d.layout->'widgets') w
GROUP BY d.name, w.value->>'type'
ORDER BY d.name, widget_type;

-- ============================================================
-- Cleanup (if needed)
-- ============================================================

-- To remove all sample dashboards:
-- DELETE FROM dashboards WHERE slug IN (
--     'shift-management-overview',
--     'realtime-operations',
--     'request-management',
--     'executive-summary',
--     'performance-monitoring'
-- );
