"""Аудит #13: не-ASCII в предъявленном токене — отказ, а не 500.

`hmac.compare_digest` на строках с не-ASCII символами бросает TypeError;
без аутентификации это давало ответ 500 вместо 401 на трёх ручках.
"""
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from uk_management_bot.api.news_watch.router import _require_service_token
from uk_management_bot.api.routes.health import require_health_token
from uk_management_bot.api.webhooks.security import verify_signature

NON_ASCII = "тест"


def test_webhook_signature_with_non_ascii_is_no_match():
    header = f"t={int(time.time())},v1={NON_ASCII}"
    assert verify_signature(b"{}", header, ["secret"]) == (False, "no_match")


@pytest.mark.asyncio
async def test_news_watch_service_token_with_non_ascii_is_401():
    with patch("uk_management_bot.api.news_watch.router.settings.NEWS_WATCH_SERVICE_TOKEN", "expected-token"):
        with pytest.raises(HTTPException) as exc:
            await _require_service_token(NON_ASCII)
    assert exc.value.status_code == 401


def test_health_token_with_non_ascii_is_401():
    with patch("uk_management_bot.api.routes.health.settings.HEALTH_METRICS_TOKEN", "expected-token"):
        with pytest.raises(HTTPException) as exc:
            require_health_token(f"Bearer {NON_ASCII}")
    assert exc.value.status_code == 401
