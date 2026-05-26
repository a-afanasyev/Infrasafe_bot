"""SEC-092 — `/test`, `/simple`, `/minimal` routes must only exist on
dev builds.

Pre-fix these three template-render routes were registered unconditionally
and reachable at the prod edge `infrasafe.uz/uk/{test,simple,minimal}`,
increasing attack surface (raw template rendering, information leakage).

The fix gates the route registration on `settings.DEBUG`. We verify by
loading the web app twice — once with DEBUG=False, once with DEBUG=True
— and inspecting the resulting route table.
"""
from __future__ import annotations

import importlib

import pytest


DEBUG_ONLY_PATHS = {"/test", "/simple", "/minimal"}


def _route_paths(app) -> set[str]:
    return {getattr(r, "path", None) for r in app.routes}


def _reload_web_main_with_debug(debug: bool):
    """Reload `uk_management_bot.web.main` so route registration runs against
    the freshly-mutated settings flag. Returns the new `app`."""
    from uk_management_bot.config import settings as settings_module

    settings_module.settings.DEBUG = debug

    import uk_management_bot.web.main as web_main
    return importlib.reload(web_main).app


def test_debug_routes_absent_when_debug_false():
    """Prod path: DEBUG=False ⇒ /test, /simple, /minimal are NOT registered."""
    app = _reload_web_main_with_debug(debug=False)
    paths = _route_paths(app)
    intersection = DEBUG_ONLY_PATHS & paths
    assert intersection == set(), (
        f"Debug-only routes leaked into prod app: {intersection}"
    )


def test_debug_routes_present_when_debug_true():
    """Dev path: DEBUG=True ⇒ all three test pages remain available."""
    app = _reload_web_main_with_debug(debug=True)
    paths = _route_paths(app)
    assert DEBUG_ONLY_PATHS.issubset(paths), (
        f"Debug routes missing on dev build: "
        f"{DEBUG_ONLY_PATHS - paths}"
    )


@pytest.fixture(autouse=True)
def _restore_debug_after_test():
    """Each test reloads the web module which mutates global state. Reset to
    a known-good debug=True at teardown so neighbour tests see dev defaults."""
    yield
    _reload_web_main_with_debug(debug=True)
