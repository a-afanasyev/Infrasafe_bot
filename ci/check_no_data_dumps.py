"""A11-CODE-11: в публичном репозитории нет дампов БД с персональными данными.

Повод: ``docs/Archive/SQL_Scripts/backup_phase2b_20251020_194140.sql`` пролежал
в публичном репо год — ``COPY public.users`` с Telegram ID, именами и телефонами.

Правила для каждого файла из ``git ls-files``:
  * бинарный pg_dump (сигнатура ``PGDMP`` в начале файла — в том числе после
    распаковки gzip) и расширения ``.dump``/``.backup``/``.pgdump`` — нарушение
    без разбора: содержимое не проверить, значит, в репо его быть не может;
  * сжатый SQL/дамп кроме gzip (``.sql.bz2``/``.xz``/``.zst``/``.zip``,
    ``.dump.*``, ``.backup.*``) — нарушение без разбора;
  * ``.sql`` — текст, ``.sql.gz`` — после распаковки; больше ``MAX_BYTES`` (файл
    или результат распаковки — защита от gzip-бомбы) и битый gzip — нарушение;
  * текст декодируется с учётом BOM/UTF-16, комментарии SQL вырезаются;
  * нарушение — ``COPY``/``INSERT INTO`` в таблицу ПДн (``PII_TABLES``) при
    любом регистре, с любой схемой или без, с кавычками и переводами строк
    между словами. Схема (``CREATE TABLE``), ``GRANT``, ``DELETE`` и другие
    таблицы проверку проходят.

Это защита от случайного коммита выгрузки, а не от намеренного обхода
(переименованный CSV/JSON с ПДн она не увидит).

Запуск — на checkout (CI-job ``lint``, ``scripts/test-ci-local.sh`` до сборки):
``python3 ci/check_no_data_dumps.py``; код выхода 1 — есть нарушения.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zlib
from pathlib import Path

PII_TABLES = (
    "users", "user_documents", "user_verifications", "account_owners",
    "user_apartments", "requests", "audit_logs",
)
MAX_BYTES = 64 * 1024 * 1024
_PGDMP = b"PGDMP"
_BINARY_DUMP_SUFFIXES = (".dump", ".backup", ".pgdump")
_OPAQUE_ARCHIVE = re.compile(r"\.(?:sql|dump|backup|pgdump)\.(?:bz2|xz|zst|zip|lz4|7z|gz)$|"
                             r"\.(?:dump|backup|pgdump)\.[a-z0-9]+$")
_FULL_READ_SUFFIXES = (".sql", ".sql.gz") + _BINARY_DUMP_SUFFIXES
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_DATA_STMT = re.compile(
    r"\b(?:COPY|INSERT\s+INTO)\s+(?:\"?\w+\"?\s*\.\s*)?\"?(" + "|".join(PII_TABLES) + r")\"?(?=[\s(;]|$)",
    re.IGNORECASE,
)
# Выгрузка запросом: COPY (SELECT … FROM users …) TO … — имени таблицы после COPY нет.
_COPY_QUERY = re.compile(
    r"\bCOPY\s*\([^;]*?\bFROM\s+(?:\"?\w+\"?\s*\.\s*)?\"?(" + "|".join(PII_TABLES) + r")\"?(?=[\s();]|$)",
    re.IGNORECASE,
)


def _gunzip_bounded(data: bytes) -> bytes | None:
    """Распаковать gzip не больше ``MAX_BYTES``; None — битый или слишком большой."""
    inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        out = inflater.decompress(data, MAX_BYTES + 1)
    except zlib.error:
        return None
    # unused_data — второй член gzip (`cat a.gz b.gz`): его не проверить → не принимаем.
    if len(out) > MAX_BYTES or inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
        return None
    return out


def _decode(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16", errors="replace")
    if b"\x00" in content[:4096]:  # UTF-16 без BOM (выгрузка из PowerShell)
        return content.decode("utf-16-le", errors="replace")
    return content.decode("utf-8-sig", errors="replace")


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", text))


def check_file(path: str, content: bytes) -> list[str]:
    """Нарушения в одном файле (пусто — чисто)."""
    lower = path.lower()
    if content[: len(_PGDMP)] == _PGDMP or lower.endswith(_BINARY_DUMP_SUFFIXES):
        return [f"{path}: бинарный дамп PostgreSQL — в репозитории запрещён"]
    if _OPAQUE_ARCHIVE.search(lower) and not lower.endswith(".sql.gz"):
        return [f"{path}: сжатый дамп/SQL (не gzip) — проверить нельзя, в репозитории запрещён"]
    if lower.endswith(".sql.gz"):
        unpacked = _gunzip_bounded(content)
        if unpacked is None:
            return [f"{path}: битый gzip или больше {MAX_BYTES} байт после распаковки — проверить нельзя"]
        if unpacked[: len(_PGDMP)] == _PGDMP:
            return [f"{path}: бинарный дамп PostgreSQL внутри gzip — в репозитории запрещён"]
        content = unpacked
    elif not lower.endswith(".sql"):
        return []
    if len(content) > MAX_BYTES:
        return [f"{path}: больше {MAX_BYTES} байт — проверить нельзя"]
    text = _strip_comments(_decode(content))
    tables = sorted({m.group(1).lower() for rx in (_DATA_STMT, _COPY_QUERY) for m in rx.finditer(text)})
    return [f"{path}: данные таблицы {t} (COPY/INSERT)" for t in tables]


def _tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8", errors="surrogateescape").split("\0") if p]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems: list[str] = []
    for rel in _tracked_files(root):
        path = root / rel
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES and rel.lower().endswith(_FULL_READ_SUFFIXES):
            problems.append(f"{rel}: больше {MAX_BYTES} байт — проверить нельзя")
            continue
        if rel.lower().endswith(_FULL_READ_SUFFIXES):
            content = path.read_bytes()
        else:
            with path.open("rb") as fh:  # остальное — только сигнатура pg_dump
                content = fh.read(len(_PGDMP))
        problems += check_file(rel, content)
    for line in problems:
        print(line, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
