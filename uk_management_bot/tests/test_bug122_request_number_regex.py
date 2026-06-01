"""BUG-122 — request_number regex inconsistency (\\d{3} vs \\d{3,}).

`RequestNumberService` already writes/validates `YYMMDD-NNN+` (3+ digits, rolls
over past 999/day), but several consumers were hardcoded to exactly 3 digits
and would reject `260524-1000`:
  - api/main.py media proxy `REQUEST_NUMBER_PATTERN`
  - handlers/requests.py cancel + view callback matchers

Fix introduces a single shared core fragment in request_number_service and
rebuilds every consumer pattern from it.
"""
import re


def test_shared_pattern_accepts_3_and_4_plus_digits():
    from uk_management_bot.services.request_number_service import (
        REQUEST_NUMBER_PATTERN,
        REQUEST_NUMBER_CORE,
    )

    assert re.match(REQUEST_NUMBER_PATTERN, "260524-001")
    assert re.match(REQUEST_NUMBER_PATTERN, "260524-1000")     # 4-digit rollover
    assert re.match(REQUEST_NUMBER_PATTERN, "260524-12345")
    assert not re.match(REQUEST_NUMBER_PATTERN, "260524-01")   # <3 digits
    assert not re.match(REQUEST_NUMBER_PATTERN, "260524-abc")
    assert REQUEST_NUMBER_CORE in REQUEST_NUMBER_PATTERN


def test_api_media_proxy_pattern_accepts_4_digit():
    from uk_management_bot.api.main import REQUEST_NUMBER_PATTERN as api_pat

    assert api_pat.match("260524-1000")
    assert api_pat.match("260524-001")
    assert not api_pat.match("260524-01")


def test_cancel_and_view_callback_regex_accept_4_digit():
    from uk_management_bot.handlers.requests import (
        _CANCEL_REQUEST_NUMBER_RE,
        _VIEW_REQUEST_NUMBER_RE,
    )

    assert _CANCEL_REQUEST_NUMBER_RE.match("cancel_260524-1000")
    assert _CANCEL_REQUEST_NUMBER_RE.match("cancel_260524-001")
    assert re.match(_VIEW_REQUEST_NUMBER_RE, "view_260524-1000")
    assert re.match(_VIEW_REQUEST_NUMBER_RE, "view_request_260524-1000")
