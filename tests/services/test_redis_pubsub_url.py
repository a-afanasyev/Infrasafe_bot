"""PR-B — Settings.REDIS_PUBSUB_URL_RESOLVED derivation logic.

The pubsub URL must inherit auth from REDIS_URL (which carries the password in
production) unless an explicit REDIS_PUBSUB_URL is provided.
"""

from uk_management_bot.config.settings import Settings


def _settings(redis_url: str, pubsub_url: str) -> Settings:
    """Build a Settings instance with the two URL attributes overridden."""
    s = Settings()
    s.REDIS_URL = redis_url
    s.REDIS_PUBSUB_URL = pubsub_url
    return s


def test_explicit_pubsub_url_wins():
    """An explicitly configured REDIS_PUBSUB_URL is returned untouched."""
    s = _settings("redis://:pwd@h:6379/0", "redis://other:6380/3")
    assert s.REDIS_PUBSUB_URL_RESOLVED == "redis://other:6380/3"


def test_derive_swaps_db0_to_db1_keeping_auth():
    """Empty pubsub URL → derive from REDIS_URL, swapping /0 → /1, auth kept."""
    s = _settings("redis://:pwd@h:6379/0", "")
    assert s.REDIS_PUBSUB_URL_RESOLVED == "redis://:pwd@h:6379/1"


def test_derive_appends_db1_when_no_db_suffix():
    """REDIS_URL without a /N suffix → append /1."""
    s = _settings("redis://h:6379", "")
    assert s.REDIS_PUBSUB_URL_RESOLVED == "redis://h:6379/1"


def test_fallback_when_both_empty():
    """Both URLs empty → static fallback to the docker-internal default."""
    s = _settings("", "")
    assert s.REDIS_PUBSUB_URL_RESOLVED == "redis://redis:6379/1"
