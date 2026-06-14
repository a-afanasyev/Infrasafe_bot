"""
Unit tests for utils/structured_logger.py

Tests StructuredFormatter, SecurityFilter, StructuredLogger,
get_logger(), get_auth_logger() etc., log_function_call decorator.
"""
import asyncio
import json
import logging
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# StructuredFormatter
# ---------------------------------------------------------------------------

class TestStructuredFormatter:
    def _make_record(self, msg: str = "test message", level=logging.INFO, **extras) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test_logger",
            level=level,
            pathname="/app/test.py",
            lineno=42,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extras.items():
            setattr(record, k, v)
        return record

    def test_format_returns_valid_json(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("hello")
            result = formatter.format(record)
        data = json.loads(result)
        assert "timestamp" in data
        assert data["message"] == "hello"

    def test_format_includes_level(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("test", level=logging.WARNING)
            result = formatter.format(record)
        data = json.loads(result)
        assert data["level"] == "WARNING"

    def test_format_debug_mode_includes_file_info(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = True
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("debug msg")
            result = formatter.format(record)
        data = json.loads(result)
        assert "file" in data
        assert "line" in data
        assert "function" in data

    def test_format_non_debug_mode_no_file_info(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("prod msg")
            result = formatter.format(record)
        data = json.loads(result)
        assert "file" not in data

    def test_format_includes_extra_fields(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("with extras", user_id=123, action="login")
            result = formatter.format(record)
        data = json.loads(result)
        assert data["user_id"] == 123
        assert data["action"] == "login"

    def test_format_includes_metadata(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("meta", metadata={"key": "val"})
            result = formatter.format(record)
        data = json.loads(result)
        assert data["metadata"] == {"key": "val"}

    def test_format_includes_request_id(self):
        with patch("uk_management_bot.utils.structured_logger.settings") as s:
            s.DEBUG = False
            from uk_management_bot.utils.structured_logger import StructuredFormatter
            formatter = StructuredFormatter()
            record = self._make_record("req", request_id="req-001", telegram_id=999)
            result = formatter.format(record)
        data = json.loads(result)
        assert data["request_id"] == "req-001"
        assert data["telegram_id"] == 999


# ---------------------------------------------------------------------------
# SecurityFilter
# ---------------------------------------------------------------------------

class TestSecurityFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="sec",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_non_sensitive_message_passes_through(self):
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        record = self._make_record("User logged in successfully")
        result = f.filter(record)
        assert result is True
        assert record.msg == "User logged in successfully"

    # NOTE: SecurityFilter does SELECTIVE redaction of key=value / key: value
    # secrets (preserving the rest of the message), not whole-message nuking.
    # Inputs must therefore carry an explicit `=`/`:` separator to be redacted.

    def test_message_with_password_gets_redacted(self):
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        record = self._make_record("password=12345")
        f.filter(record)
        assert record.msg == "password= [REDACTED]"
        assert "12345" not in record.msg

    def test_message_with_token_gets_redacted(self):
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        record = self._make_record("token: abc123")
        f.filter(record)
        assert record.msg == "token: [REDACTED]"
        assert "abc123" not in record.msg

    def test_message_with_secret_gets_redacted(self):
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        record = self._make_record("secret=xyz")
        f.filter(record)
        assert record.msg == "secret= [REDACTED]"
        assert "xyz" not in record.msg

    def test_filter_always_returns_true(self):
        """SecurityFilter always returns True (never drops log records)."""
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        for msg in ["password=secret", "token=abc", "normal message"]:
            record = self._make_record(msg)
            assert f.filter(record) is True

    def test_sensitive_patterns_case_insensitive(self):
        from uk_management_bot.utils.structured_logger import SecurityFilter
        f = SecurityFilter()
        record = self._make_record("PASSWORD=hunter2")  # uppercase key still matches
        f.filter(record)
        assert record.msg == "PASSWORD= [REDACTED]"
        assert "hunter2" not in record.msg


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------

class TestStructuredLogger:
    def test_info_logs_message(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.structured")
        with patch.object(logger.logger, "log") as mock_log:
            logger.info("hello info")
        mock_log.assert_called_once()
        args = mock_log.call_args
        assert args[0][1] == "hello info"

    def test_debug_logs_at_debug_level(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.debug")
        with patch.object(logger.logger, "log") as mock_log:
            logger.debug("debug msg")
        mock_log.assert_called_once()
        assert mock_log.call_args[0][0] == logging.DEBUG

    def test_warning_logs_at_warning_level(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.warn")
        with patch.object(logger.logger, "log") as mock_log:
            logger.warning("warn msg")
        assert mock_log.call_args[0][0] == logging.WARNING

    def test_error_logs_at_error_level(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.error")
        with patch.object(logger.logger, "log") as mock_log:
            logger.error("error msg")
        assert mock_log.call_args[0][0] == logging.ERROR

    def test_critical_logs_at_critical_level(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.critical")
        with patch.object(logger.logger, "log") as mock_log:
            logger.critical("critical msg")
        assert mock_log.call_args[0][0] == logging.CRITICAL

    def test_with_context_creates_new_logger(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.ctx", component="auth")
        child = logger.with_context(user_id=42)
        assert isinstance(child, StructuredLogger)
        assert child.context.get("user_id") == 42
        assert child.context.get("component") == "auth"

    def test_context_in_extra(self):
        from uk_management_bot.utils.structured_logger import StructuredLogger
        logger = StructuredLogger("test.extra", component="shifts")
        with patch.object(logger.logger, "log") as mock_log:
            logger.info("shift started", shift_id=7)
        extra = mock_log.call_args[1]["extra"]
        assert extra.get("component") == "shifts"
        assert extra.get("shift_id") == 7


# ---------------------------------------------------------------------------
# get_logger and predefined loggers
# ---------------------------------------------------------------------------

class TestGetLogger:
    def test_get_logger_returns_structured_logger(self):
        from uk_management_bot.utils.structured_logger import get_logger, StructuredLogger
        result = get_logger("test.module")
        assert isinstance(result, StructuredLogger)

    def test_get_logger_with_context(self):
        from uk_management_bot.utils.structured_logger import get_logger
        result = get_logger("test.ctx", component="requests")
        assert result.context.get("component") == "requests"

    def test_get_auth_logger_has_component(self):
        from uk_management_bot.utils.structured_logger import get_auth_logger
        result = get_auth_logger()
        assert result.context.get("component") == "auth"

    def test_get_request_logger_has_component(self):
        from uk_management_bot.utils.structured_logger import get_request_logger
        result = get_request_logger()
        assert result.context.get("component") == "requests"

    def test_get_shift_logger_has_component(self):
        from uk_management_bot.utils.structured_logger import get_shift_logger
        result = get_shift_logger()
        assert result.context.get("component") == "shifts"

    def test_get_security_logger_has_component(self):
        from uk_management_bot.utils.structured_logger import get_security_logger
        result = get_security_logger()
        assert result.context.get("component") == "security"

    def test_get_performance_logger_has_component(self):
        from uk_management_bot.utils.structured_logger import get_performance_logger
        result = get_performance_logger()
        assert result.context.get("component") == "performance"


# ---------------------------------------------------------------------------
# log_function_call decorator
# ---------------------------------------------------------------------------

class TestLogFunctionCallDecorator:
    def test_sync_function_called_normally(self):
        from uk_management_bot.utils.structured_logger import log_function_call, get_logger
        logger = get_logger("test.decorator")

        @log_function_call(logger=logger)
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5

    def test_sync_function_exception_re_raised(self):
        from uk_management_bot.utils.structured_logger import log_function_call, get_logger
        logger = get_logger("test.decorator2")

        @log_function_call(logger=logger)
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

    def test_async_function_called_normally(self):
        from uk_management_bot.utils.structured_logger import log_function_call, get_logger
        logger = get_logger("test.async_decorator")

        @log_function_call(logger=logger)
        async def async_add(a, b):
            return a + b

        result = asyncio.get_event_loop().run_until_complete(async_add(3, 4))
        assert result == 7

    def test_async_function_exception_re_raised(self):
        from uk_management_bot.utils.structured_logger import log_function_call, get_logger
        logger = get_logger("test.async_decorator3")

        @log_function_call(logger=logger)
        async def async_fail():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            asyncio.get_event_loop().run_until_complete(async_fail())

    def test_decorator_without_explicit_logger(self):
        """When no logger passed, one is created automatically."""
        from uk_management_bot.utils.structured_logger import log_function_call

        @log_function_call()
        def multiply(a, b):
            return a * b

        assert multiply(3, 4) == 12

    def test_info_level_used(self):
        from uk_management_bot.utils.structured_logger import log_function_call, get_logger
        logger = get_logger("test.level")

        calls = []
        original_info = logger.info
        logger.info = lambda msg, **kw: calls.append(("info", msg))

        @log_function_call(logger=logger, level="info")
        def greet(name):
            return f"Hello {name}"

        greet("World")
        assert any("info" == lvl for lvl, _ in calls)
