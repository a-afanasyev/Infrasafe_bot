"""
Test FastAPI application without problematic middleware
Used for integration tests to avoid anyio/event loop conflicts
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from api.v1 import shifts, templates, analytics, assignments, transfers, internal, schedule

# Create test app WITHOUT BaseHTTPMiddleware (which uses anyio TaskGroup)
test_app = FastAPI(
    title="Shift Service Test",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS (doesn't use anyio)
test_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple middleware to inject test user (function-based, not BaseHTTPMiddleware)
@test_app.middleware("http")
async def add_test_user_middleware(request: Request, call_next):
    """Inject test user into request state for all requests"""
    request.state.user = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "username": "test_user",
        "role": "manager",
        "permissions": ["shift:*"]
    }
    response = await call_next(request)
    return response

# Include routers
test_app.include_router(shifts.router, prefix="/api/v1/shifts", tags=["shifts"])
test_app.include_router(templates.router, prefix="/api/v1/templates", tags=["templates"])
test_app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
test_app.include_router(assignments.router, prefix="/api/v1/assignments", tags=["assignments"])
test_app.include_router(transfers.router, prefix="/api/v1/transfers", tags=["transfers"])
test_app.include_router(internal.router, prefix="/api/v1/internal", tags=["internal"])
test_app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])
