import logging

from uk_management_bot.utils.structured_logger import SecurityFilter


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)


def test_redacts_password_value():
    f = SecurityFilter()
    record = _make_record("User login password=secret123")
    f.filter(record)
    assert "secret123" not in record.getMessage()
    assert "login" in record.getMessage()


def test_preserves_auth_middleware_message():
    f = SecurityFilter()
    record = _make_record("Auth middleware initialized")
    f.filter(record)
    assert "Auth middleware initialized" in record.getMessage()


def test_redacts_bearer_token():
    f = SecurityFilter()
    record = _make_record("Authorization: Bearer eyJabc123")
    f.filter(record)
    assert "eyJabc123" not in record.getMessage()
    assert "Authorization:" in record.getMessage()


def test_redacts_token_with_equals():
    f = SecurityFilter()
    record = _make_record("Received token=abc123xyz from client")
    f.filter(record)
    assert "abc123xyz" not in record.getMessage()
    assert "token=" in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_redacts_secret_with_colon():
    f = SecurityFilter()
    record = _make_record("Config loaded secret: my_secret_value")
    f.filter(record)
    assert "my_secret_value" not in record.getMessage()
    assert "secret:" in record.getMessage()


def test_redacts_bot_token_pattern():
    f = SecurityFilter()
    record = _make_record("Starting Bot 123456789:ABCdefGHIjklMNO_pqr")
    f.filter(record)
    assert "123456789:ABCdefGHIjklMNO_pqr" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_preserves_normal_message():
    f = SecurityFilter()
    record = _make_record("User created request #240101-001")
    f.filter(record)
    assert "User created request #240101-001" in record.getMessage()


def test_redacts_api_key_value():
    f = SecurityFilter()
    record = _make_record("Using api_key=sk-12345abcde for service")
    f.filter(record)
    assert "sk-12345abcde" not in record.getMessage()
    assert "api_key=" in record.getMessage()
