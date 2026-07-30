"""AUD6-P2-41: AST-гейт против локальных копий `_utcnow`.

Побайтово идентичные `def _utcnow(): return datetime.now(timezone.utc)` жили
в 15 файлах при существующем каноне `utils/datetime_utils.utc_now`
(AUD5-CODE-3) — ровно тот класс расползания, что уже стрелял tz-багами.
Локальные обёртки запрещены: импортировать канон (в т.ч. алиасом
`import utc_now as _utcnow` — это разрешено, дрейфовать в алиасе нечему).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCOPES = ("uk_management_bot", "access_control")
CANON = ROOT / "uk_management_bot" / "utils" / "datetime_utils.py"
FORBIDDEN_NAMES = {"_utcnow", "utcnow", "utc_now", "_utc_now"}


def _prod_files():
    for scope in SCOPES:
        for path in (ROOT / scope).rglob("*.py"):
            # venv/site-packages: у разработчиков на диске может лежать
            # нетрекнутый uk_management_bot/venv (AUD6-P3-44) — не сканируем.
            if {"tests", "venv", "site-packages"} & set(path.parts):
                continue
            if path == CANON:
                continue
            yield path


def test_no_local_utcnow_definitions():
    offenders = []
    for path in _prod_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:  # сломанный файл — отдельная проблема, но не молчим
            offenders.append(f"{path}: не парсится ({e})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FORBIDDEN_NAMES:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: def {node.name}")
    assert not offenders, (
        "Локальная копия utcnow вместо канона utils/datetime_utils.utc_now "
        "(AUD6-P2-41):\n" + "\n".join(offenders)
    )
