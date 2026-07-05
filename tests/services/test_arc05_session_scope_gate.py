"""ARC-05 SSOT-гейт: мигрированные файлы не должны содержать legacy `next(get_db())`.

Зеркалит паттерн CODE-04 (tests/services/test_shift_management_inventory.py):
скан живого кода (без комментариев/докстрингов) на запрещённую идиому.
Список MIGRATED_FILES расширяется по мере миграции файлов в будущих FU-PR.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MIGRATED_FILES = [
    ROOT / "uk_management_bot" / "handlers" / "inspector_requests.py",
    ROOT / "uk_management_bot" / "handlers" / "request_acceptance.py",
]

_NEXT_GET_DB = re.compile(r"next\(\s*get_db\(\)\s*\)")


def test_migrated_files_have_no_next_get_db():
    """В мигрированных файлах — только `session_scope()` / `_db_scope`, без `next(get_db())`."""
    matches = []
    for path in MIGRATED_FILES:
        assert path.exists(), f"missing migrated file: {path}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            # исключаем строки-комментарии и docstring-упоминания (``...``)
            if stripped.startswith("#") or "``" in line:
                continue
            if _NEXT_GET_DB.search(line):
                matches.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not matches, (
        "ARC-05: найден legacy `next(get_db())` в мигрированных файлах "
        "(используйте `with session_scope() as db:` или `_db_scope`):\n"
        + "\n".join(matches)
    )
