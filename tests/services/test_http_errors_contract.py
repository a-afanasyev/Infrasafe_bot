"""E1 — контракт двух копий describe_http_error (бот ↔ media-service).

Копии две по построению: media — отдельный контейнер, импортировать
`uk_management_bot` не может (образ содержит только app/). Расхождение копий
означало бы, что один сервис логирует токен, считая формат «безопасным».
Приём — test_media_sniff_contract.py: функция media вытаскивается по AST.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from uk_management_bot.utils.http_errors import describe_http_error as bot_describe

ROOT = Path(__file__).resolve().parents[2]
MEDIA_SANITIZE = ROOT / "media_service" / "app" / "core" / "log_sanitize.py"


def _load_media_describe():
    tree = ast.parse(MEDIA_SANITIZE.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "describe_http_error")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(MEDIA_SANITIZE), "exec"), ns)
    return ns["describe_http_error"]


media_describe = _load_media_describe()


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


class _HttpStatusError(Exception):
    def __init__(self, status):
        super().__init__("Server error for url 'https://api.telegram.org/bot123:SECRET/getFile'")
        self.response = _Resp(status)


class _ConnectError(Exception):
    pass


@pytest.mark.parametrize("exc", [
    _HttpStatusError(500),
    _HttpStatusError(429),
    _ConnectError("boom"),
    TimeoutError(),
])
def test_both_copies_agree(exc):
    assert bot_describe(exc) == media_describe(exc)


@pytest.mark.parametrize("exc", [_HttpStatusError(500), _ConnectError("x")])
def test_no_url_or_token_in_output(exc):
    for fn in (bot_describe, media_describe):
        out = fn(exc)
        assert "api.telegram.org" not in out and "SECRET" not in out
