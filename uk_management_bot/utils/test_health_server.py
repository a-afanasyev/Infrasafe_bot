"""
Unit tests for utils/health_server.py

Tests HealthCheckHandler request handling, HealthServer lifecycle,
and global helper functions. HTTP handling tested via direct method calls
without starting a real socket.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, call
from io import BytesIO


# ---------------------------------------------------------------------------
# Helpers — minimal fake request for HealthCheckHandler
# ---------------------------------------------------------------------------

def _make_handler(path: str = "/health"):
    """Create a HealthCheckHandler instance without starting a real server."""
    from uk_management_bot.utils.health_server import HealthCheckHandler

    # BytesIO buffer to capture response output
    buf = BytesIO()

    handler = HealthCheckHandler.__new__(HealthCheckHandler)
    handler.path = path
    handler.wfile = buf

    # Stubs for BaseHTTPRequestHandler methods
    sent_responses = []
    sent_headers = []
    headers_ended = []

    handler.send_response = lambda code: sent_responses.append(code)
    handler.send_header = lambda k, v: sent_headers.append((k, v))
    handler.end_headers = lambda: headers_ended.append(True)

    handler._responses_sent = sent_responses
    handler._headers_sent = sent_headers
    handler._headers_ended = headers_ended

    return handler


def _get_json_output(handler):
    handler.wfile.seek(0)
    raw = handler.wfile.read()
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# HealthCheckHandler._handle_ping
# ---------------------------------------------------------------------------

class TestHealthCheckHandlerPing:
    def test_ping_sends_200(self):
        handler = _make_handler("/ping")
        handler._handle_ping()
        assert 200 in handler._responses_sent

    def test_ping_returns_ok_status(self):
        handler = _make_handler("/ping")
        handler._handle_ping()
        data = _get_json_output(handler)
        assert data["status"] == "ok"
        assert data["message"] == "pong"

    def test_ping_response_has_timestamp(self):
        handler = _make_handler("/ping")
        handler._handle_ping()
        data = _get_json_output(handler)
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# HealthCheckHandler._send_404
# ---------------------------------------------------------------------------

class TestHealthCheckHandler404:
    def test_sends_404_code(self):
        handler = _make_handler("/nonexistent")
        handler._send_404()
        assert 404 in handler._responses_sent

    def test_404_body_has_error_key(self):
        handler = _make_handler("/nonexistent")
        handler._send_404()
        data = _get_json_output(handler)
        assert "error" in data

    def test_404_body_mentions_available_endpoints(self):
        handler = _make_handler("/nonexistent")
        handler._send_404()
        data = _get_json_output(handler)
        assert "/health" in data.get("message", "")


# ---------------------------------------------------------------------------
# HealthCheckHandler.do_GET routing
# ---------------------------------------------------------------------------

class TestHealthCheckHandlerDoGet:
    def test_routes_health_path(self):
        handler = _make_handler("/health")
        with patch.object(handler, "_handle_health_check") as mock_health:
            handler.do_GET()
        mock_health.assert_called_once()

    def test_routes_ping_path(self):
        handler = _make_handler("/ping")
        with patch.object(handler, "_handle_ping") as mock_ping:
            handler.do_GET()
        mock_ping.assert_called_once()

    def test_routes_unknown_path_to_404(self):
        handler = _make_handler("/unknown")
        with patch.object(handler, "_send_404") as mock_404:
            handler.do_GET()
        mock_404.assert_called_once()


# ---------------------------------------------------------------------------
# HealthCheckHandler._handle_health_check (mocked DB)
# ---------------------------------------------------------------------------

class TestHealthCheckHandlerHealth:
    def test_healthy_when_db_ok(self):
        handler = _make_handler("/health")

        mock_db = MagicMock()
        mock_db.execute.return_value = None

        with patch("uk_management_bot.utils.health_server.SessionLocal", return_value=mock_db):
            handler._handle_health_check()

        assert 200 in handler._responses_sent

    def test_unhealthy_when_db_fails(self):
        handler = _make_handler("/health")

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB connection failed")

        with patch("uk_management_bot.utils.health_server.SessionLocal", return_value=mock_db):
            handler._handle_health_check()

        assert 503 in handler._responses_sent

    def test_health_response_has_status_field(self):
        handler = _make_handler("/health")

        mock_db = MagicMock()
        mock_db.execute.return_value = None

        with patch("uk_management_bot.utils.health_server.SessionLocal", return_value=mock_db):
            handler._handle_health_check()

        data = _get_json_output(handler)
        assert "status" in data

    def test_db_always_closed(self):
        """SessionLocal.close() must be called even if execute() raises."""
        handler = _make_handler("/health")
        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("boom")

        with patch("uk_management_bot.utils.health_server.SessionLocal", return_value=mock_db):
            handler._handle_health_check()

        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# HealthServer
# ---------------------------------------------------------------------------

class TestHealthServer:
    def test_start_sets_running_true(self):
        from uk_management_bot.utils.health_server import HealthServer

        hs = HealthServer(host="127.0.0.1", port=9999)

        mock_httpserver = MagicMock()
        mock_thread = MagicMock()

        with patch("uk_management_bot.utils.health_server.HTTPServer", return_value=mock_httpserver), \
             patch("uk_management_bot.utils.health_server.Thread", return_value=mock_thread):
            hs.start()

        assert hs.running is True
        mock_thread.start.assert_called_once()

    def test_start_twice_does_not_start_second_thread(self):
        from uk_management_bot.utils.health_server import HealthServer

        hs = HealthServer(host="127.0.0.1", port=9998)
        hs.running = True  # Simulate already running

        with patch("uk_management_bot.utils.health_server.HTTPServer") as mock_httpserver_cls, \
             patch("uk_management_bot.utils.health_server.Thread") as mock_thread_cls:
            hs.start()

        mock_httpserver_cls.assert_not_called()
        mock_thread_cls.assert_not_called()

    def test_stop_calls_shutdown(self):
        from uk_management_bot.utils.health_server import HealthServer

        hs = HealthServer()
        hs.running = True
        hs.server = MagicMock()

        hs.stop()

        hs.server.shutdown.assert_called_once()
        hs.server.server_close.assert_called_once()
        assert hs.running is False

    def test_stop_when_not_running_is_noop(self):
        from uk_management_bot.utils.health_server import HealthServer

        hs = HealthServer()
        hs.running = False
        hs.server = MagicMock()

        hs.stop()  # Should not raise or call server methods

        hs.server.shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# Global helper functions
# ---------------------------------------------------------------------------

class TestGlobalHelperFunctions:
    def setup_method(self):
        """Reset global server state before each test."""
        import uk_management_bot.utils.health_server as hs_mod
        hs_mod._health_server = None

    def test_start_health_server_creates_server(self):
        import uk_management_bot.utils.health_server as hs_mod

        mock_server_instance = MagicMock()
        with patch("uk_management_bot.utils.health_server.HealthServer", return_value=mock_server_instance):
            from uk_management_bot.utils.health_server import start_health_server
            result = start_health_server(host="127.0.0.1", port=18000)

        mock_server_instance.start.assert_called_once()
        assert result is mock_server_instance

    def test_start_health_server_returns_existing(self):
        import uk_management_bot.utils.health_server as hs_mod
        existing = MagicMock()
        hs_mod._health_server = existing

        with patch("uk_management_bot.utils.health_server.HealthServer") as mock_cls:
            from uk_management_bot.utils.health_server import start_health_server
            result = start_health_server()

        mock_cls.assert_not_called()
        assert result is existing

    def test_stop_health_server_stops_and_clears(self):
        import uk_management_bot.utils.health_server as hs_mod
        mock_server = MagicMock()
        hs_mod._health_server = mock_server

        from uk_management_bot.utils.health_server import stop_health_server
        stop_health_server()

        mock_server.stop.assert_called_once()
        assert hs_mod._health_server is None

    def test_stop_health_server_when_none_is_noop(self):
        import uk_management_bot.utils.health_server as hs_mod
        hs_mod._health_server = None
        from uk_management_bot.utils.health_server import stop_health_server
        stop_health_server()  # Should not raise

    def test_get_health_server_returns_instance(self):
        import uk_management_bot.utils.health_server as hs_mod
        from uk_management_bot.utils.health_server import HealthServer
        fake = MagicMock(spec=HealthServer)
        hs_mod._health_server = fake
        from uk_management_bot.utils.health_server import get_health_server
        result = get_health_server()
        assert result is fake

    def test_get_health_server_returns_none_when_not_started(self):
        import uk_management_bot.utils.health_server as hs_mod
        hs_mod._health_server = None
        from uk_management_bot.utils.health_server import get_health_server
        assert get_health_server() is None
