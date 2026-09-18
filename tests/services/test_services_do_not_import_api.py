"""AUD7-ARCH-02: сервисы домена не импортируют HTTP-пакет `uk_management_bot.api`.

Общие правила и схемы, которыми пользуются и роутеры, и домен, живут в
services/integrations; API-пакет импортирует их оттуда, а не наоборот.
До правки домен тянул `api.shifts.service` (residents), `api.board_config.service`
(work_reports) и `api.webhooks.{mappings,replay,schemas}` (inbound_alert) — правка
HTTP-пакета задевала домен. Цикла не было, задача — о размещении. Гейт
статический (AST), без allowlist: новое ребро services → api = красный тест.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "uk_management_bot" / "services"
API_PREFIX = "uk_management_bot.api"


def _api_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == API_PREFIX or node.module.startswith(API_PREFIX + "."):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.module}")
            elif node.module == "uk_management_bot" and any(a.name == "api" for a in node.names):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno} api")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == API_PREFIX or a.name.startswith(API_PREFIX + "."):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno} {a.name}")
    return hits


def _prod_files():
    for path in sorted(SERVICES.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or path.name.startswith("test_"):
            continue
        yield path


def test_services_do_not_import_api_package():
    hits = [h for p in _prod_files() for h in _api_imports(p)]
    assert not hits, "домен импортирует HTTP-пакет api (перенести общий модуль в services/integrations):\n" + "\n".join(hits)
