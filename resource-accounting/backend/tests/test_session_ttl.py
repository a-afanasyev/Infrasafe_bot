"""AUD7-SEC-03: окно отзыва доступа к ресурсу = TTL сессии — не больше часа."""
from app.config import Settings


def test_session_ttl_bounds_revocation_window():
    assert Settings().session_ttl_seconds <= 3600
