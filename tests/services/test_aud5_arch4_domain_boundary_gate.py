"""AUD5-ARCH-4 (A7) — граница ядро ↔ access_control: contract-слой как гейт.

Решение владельца 2026-07-27: дешёвая половина (гейт) — сейчас, дорогую
(физическую развязку) не начинать, пока нет намерения разносить сервисы по
контейнерам. Гейт ценен и без развязки: он фиксирует границу до того, как её
пересечёт следующий модуль.

Контракт, зафиксированный инвентаризацией 2026-08-09 (AST, оба направления):

* access_control смотрит в ядро ТОЛЬКО через модули из CORE_SURFACE_FOR_ACCESS —
  это де-факто contract-слой: инфраструктура (сессии БД, настройки, время),
  auth-поверхность API (dependencies, auth.service, ws.router) и модель User.
  Импорт любого ДРУГОГО модуля ядра (хендлеров, сервисов бота, клавиатур…) —
  расширение поверхности; если оно осознанно, модуль добавляется в список
  ЗДЕСЬ, в том же PR, с пониманием, что это удорожает будущую развязку.

* ядро смотрит в access_control ровно двумя рёбрами (BOT_TO_ACCESS_EDGES) —
  бот-хендлер QR-кодов и подписчик уведомлений жителям. Это направление
  опаснее для развязки (оно делает access_control невыделяемым), поэтому
  гранулярность жёстче: файл → модуль, новое ребро = красный тест.

Оба списка — ратчет в обе стороны: исчезнувшее ребро/модуль обязано быть
убрано из списка (stale-запись = тоже красный), иначе список тихо врёт.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Поверхность ядра, доступная access_control (контракт-слой).
CORE_SURFACE_FOR_ACCESS = {
    "uk_management_bot.api.auth.service",
    "uk_management_bot.api.dependencies",
    "uk_management_bot.api.ws.router",
    "uk_management_bot.config.settings",
    "uk_management_bot.database.models.user",
    "uk_management_bot.database.session",
    "uk_management_bot.utils.auth_helpers",
    "uk_management_bot.utils.datetime_utils",
}

# Рёбра ядро → access_control (файл, импортируемый модуль).
BOT_TO_ACCESS_EDGES = {
    ("uk_management_bot/handlers/access_control.py",
     "access_control.services.resident"),
    ("uk_management_bot/services/access_notify_subscriber.py",
     "access_control.services.resident_notify"),
}


def _prod_files(pkg: str):
    for path in sorted((ROOT / pkg).rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or rel.endswith("conftest.py"):
            continue
        if "/test_" in rel or rel.rsplit("/", 1)[-1].startswith("test_"):
            continue
        yield rel, path


def _imports(path: Path, prefix: str, known: set[str]) -> set[str]:
    """Импортированные модули пакета ``prefix`` в файле.

    Нормализация стиля (находка ревью): ``from a.b import c`` записывается как
    ``a.b.c``, если полный путь есть в ``known`` (список гейта) — иначе как
    ``a.b``. Без этого разрешённая зависимость, записанная другим стилем
    импорта, давала бы ложное «новое ребро» (fails closed, но шумит).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == prefix or alias.name.startswith(prefix + "."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == prefix or node.module.startswith(prefix + "."):
                joined = {f"{node.module}.{alias.name}" for alias in node.names}
                matched = joined & known
                found.update(matched if matched else {node.module})
    return found


def test_access_control_imports_core_only_through_contract_surface():
    problems: list[str] = []
    seen_surface: set[str] = set()
    for rel, path in _prod_files("access_control"):
        for mod in _imports(path, "uk_management_bot", CORE_SURFACE_FOR_ACCESS):
            if mod in CORE_SURFACE_FOR_ACCESS:
                seen_surface.add(mod)
            else:
                problems.append(
                    f"{rel}: импорт {mod} — вне contract-слоя ядра "
                    "(расширение поверхности требует явного решения: "
                    "добавь модуль в CORE_SURFACE_FOR_ACCESS в этом же PR)"
                )
    stale = CORE_SURFACE_FOR_ACCESS - seen_surface
    for mod in sorted(stale):
        problems.append(
            f"CORE_SURFACE_FOR_ACCESS: {mod} больше никем не импортируется — "
            "убери из списка, поверхность сузилась (это хорошо)"
        )
    assert not problems, "AUD5-ARCH-4 граница:\n" + "\n".join(sorted(problems))


def test_core_imports_access_control_only_via_known_edges():
    problems: list[str] = []
    seen_edges: set[tuple[str, str]] = set()
    known_access_mods = {mod for _, mod in BOT_TO_ACCESS_EDGES}
    for rel, path in _prod_files("uk_management_bot"):
        for mod in _imports(path, "access_control", known_access_mods):
            edge = (rel, mod)
            if edge in BOT_TO_ACCESS_EDGES:
                seen_edges.add(edge)
            else:
                problems.append(
                    f"{rel}: импорт {mod} — новое ребро ядро→access_control; "
                    "это направление делает access_control невыделяемым, "
                    "новое ребро — только осознанным решением "
                    "(добавь в BOT_TO_ACCESS_EDGES в этом же PR)"
                )
    stale = BOT_TO_ACCESS_EDGES - seen_edges
    for rel, mod in sorted(stale):
        problems.append(
            f"BOT_TO_ACCESS_EDGES: ребро {rel} → {mod} исчезло — убери из списка"
        )
    assert not problems, "AUD5-ARCH-4 граница:\n" + "\n".join(sorted(problems))


def test_gate_lists_are_not_empty():
    """Гейт не должен тихо превратиться в пустышку при рефакторинге."""
    assert CORE_SURFACE_FOR_ACCESS and BOT_TO_ACCESS_EDGES
