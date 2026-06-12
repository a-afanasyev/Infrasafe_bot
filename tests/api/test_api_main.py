"""Tests for API main module (uk_management_bot/api/main.py).

Covers the limiter instance, CORS config, and app structure.
Does not start a test server — only inspects the configured app object.
"""
import pytest

from uk_management_bot.api.main import app, limiter


class TestAppSetup:

    def test_app_title(self):
        assert app.title == "UK Management API"

    def test_app_version(self):
        assert app.version == "2.0.0"

    def test_limiter_instance_exists(self):
        assert limiter is not None
        assert app.state.limiter is limiter

    def test_health_route_registered(self):
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_auth_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/auth" in r for r in routes)

    def test_requests_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/requests" in r for r in routes)

    def test_profile_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/profile" in r for r in routes)

    def test_shifts_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/shifts" in r for r in routes)

    def test_addresses_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/addresses" in r for r in routes)

    def test_callcenter_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/callcenter" in r for r in routes)

    def test_notifications_routes_not_registered(self):
        """DEAD-08 (PR-11): api/notifications удалён — роуты не должны
        регистрироваться; мёртвый эндпоинт не возвращается молча."""
        routes = [r.path for r in app.routes]
        assert not any("/api/v2/notifications" in r for r in routes)

    def test_profile_documents_route_not_registered(self):
        """DEAD-07 (PR-11): POST /profile/documents удалён."""
        routes = [r.path for r in app.routes]
        assert not any("/api/v2/profile/documents" in r for r in routes)

    def test_websocket_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/ws/v2" in r for r in routes)

    def test_media_upload_route_registered(self):
        routes = [r.path for r in app.routes]
        assert "/api/v2/media/upload" in routes

    def test_announcements_route_registered(self):
        routes = [r.path for r in app.routes]
        assert "/api/v2/announcements" in routes

    def test_cors_middleware_present(self):
        # FastAPI stores middleware as Middleware objects with .cls attribute
        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert any("CORS" in name for name in middleware_classes)

    def test_executor_shifts_routes_registered(self):
        routes = [r.path for r in app.routes]
        assert any("/api/v2/executor/shifts" in r for r in routes)
