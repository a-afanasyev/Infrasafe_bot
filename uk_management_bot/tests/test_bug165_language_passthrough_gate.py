"""BUG-165 — гейт класса «потерянного языка» (AST-скан из PR #452, доведён).

Класс: async-хендлер объявляет параметр ``language``, а вызывающий не передаёт
его ни позиционно, ни kwarg'ом — побеждает дефолт «ru», и узбекоязычный
пользователь получает русский экран. Дефект ничего не роняет и виден только по
языку текста, поэтому обычные тесты его не ловят — отсюда гейт по факту
вызова.

Скан сознательно узкий, чтобы не ловить ложное:
  * только ``await f(...)`` по прямому имени — методы сервисов с теми же
    именами, что у хендлеров (``svc.list_new_requests``), не считаются;
  * вызов с ``**kwargs`` пропускается — судить о содержимом нельзя.

Правило для нового кода: либо передайте язык (``language=lang``), либо, если
дефолт выбран осознанно, напишите ``language="ru"`` ЯВНО — kwarg удовлетворяет
гейт и фиксирует решение в коде.
"""
from __future__ import annotations

import ast
import pathlib

# От файла теста, не от uk_management_bot.__file__: у пакета в importlib-режиме
# с conftest-стабами __file__ может быть None.
HANDLERS_ROOT = pathlib.Path(__file__).resolve().parent.parent / "handlers"


def _language_call_sites_without_language() -> list[str]:
    targets: dict[str, int] = {}
    trees: list[tuple[pathlib.Path, ast.AST]] = []
    for path in sorted(HANDLERS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        trees.append((path, tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                names = [a.arg for a in node.args.args]
                if "language" in names:
                    targets[node.name] = names.index("language")

    hits: list[str] = []
    for path, tree in trees:
        for outer in ast.walk(tree):
            if not isinstance(outer, ast.Await) or not isinstance(
                    outer.value, ast.Call):
                continue
            call = outer.value
            if not isinstance(call.func, ast.Name):
                continue
            name = call.func.id
            if name not in targets:
                continue
            if any(kw.arg == "language" for kw in call.keywords):
                continue
            if any(kw.arg is None for kw in call.keywords):  # **kwargs
                continue
            if len(call.args) > targets[name]:
                continue
            rel = path.relative_to(HANDLERS_ROOT.parent.parent)
            hits.append(f"{rel}:{call.lineno} -> {name}()")
    return hits


def test_no_language_lost_between_handlers():
    hits = _language_call_sites_without_language()
    assert hits == [], (
        "«Потерянный язык» (BUG-165): вызов хендлера с параметром language без "
        "его передачи — получатель отрендерит экран на 'ru' независимо от "
        "языка пользователя. Передайте language (или явный language=\"ru\", "
        "если дефолт осознан):\n  " + "\n  ".join(hits)
    )


# ══════════════════════════════════════════════════════════════════════════
# Две протяжки волны (у вызывающего language не было в сигнатуре вовсе) —
# проверяется ФАКТ проброса, не отрендеренный текст (стиль PR #452: дефект
# виден только по языку строки, ассерт на фразу хрупок).
# ══════════════════════════════════════════════════════════════════════════

import pytest  # noqa: E402


class TestThreadedLanguage:
    @pytest.mark.asyncio
    async def test_login_command_threads_language(self, monkeypatch):
        from types import SimpleNamespace

        from uk_management_bot.handlers import auth as mod

        seen = {}

        async def _spy(message, user_status=None, language="ru", *, _db=None):
            seen["language"] = language

        monkeypatch.setattr(mod, "login_via_button", _spy)
        await mod.login_command(SimpleNamespace(), language="uz")
        assert seen["language"] == "uz"

    @pytest.mark.asyncio
    async def test_complete_onboarding_final_threads_language(self, monkeypatch):
        from types import SimpleNamespace

        from uk_management_bot.handlers import onboarding as mod

        seen = {}

        async def _spy(message, state, language="ru", *, _db=None):
            seen["language"] = language

        monkeypatch.setattr(mod, "complete_onboarding_with_documents", _spy)
        await mod.complete_onboarding_final(
            SimpleNamespace(), SimpleNamespace(), language="uz")
        assert seen["language"] == "uz"
