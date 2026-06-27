"""Hash-chain для append-only таблиц (§9.7, решение CTO #9).

``row_hash = sha256(prev_hash ‖ canonical_json(строки без hash-полей))``,
``prev_hash`` — ``row_hash`` предыдущей записи цепочки той же таблицы (per-table).
Вычисляется в сервисном слое ПЕРЕД вставкой (триггер §9.7 запрещает UPDATE).

Имена таблиц append-only — доверенные константы домена, НО интерполируются в SQL,
поэтому дополнительно проверяются по allowlist ``_ALLOWED`` (defence-in-depth от
latent SQL-инъекции по ``table_name``): неизвестное имя → ``ValueError``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import zlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Только эти append-only таблицы несут hash-chain (§9.7). Жёсткий allowlist —
# единственный источник имён для интерполяции в SQL ниже.
_ALLOWED = frozenset(
    {"access_decisions", "access_events", "manual_openings", "access_audit_logs"}
)


def _json_default(value: Any) -> str:
    """Явный энкодер для canonical_json: ``datetime`` → ISO-8601, иначе ``TypeError``.

    Детерминизм hash требует, чтобы неизвестные типы НЕ сериализовались молча
    (как делал ``default=str``) — это исключает скрытый дрейф row_hash.
    """
    if isinstance(value, dt.datetime):
        return value.isoformat()
    raise TypeError(
        f"canonical_json: несериализуемый тип {type(value).__name__} в payload "
        "(допустимы только JSON-примитивы и datetime)"
    )


def _canonical_json(payload: dict[str, Any]) -> str:
    """Детерминированная сериализация строки: сортированные ключи, без пробелов."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        ensure_ascii=False,
    )


def _table_lock_key(table_name: str) -> int:
    """Детерминированный int-ключ advisory-lock для цепочки таблицы (per-table)."""
    return zlib.crc32(table_name.encode("utf-8")) & 0x7FFFFFFF


def next_hash(db: Session, table_name: str, payload: dict[str, Any]) -> tuple[str | None, str]:
    """Вернуть ``(prev_hash, row_hash)`` для следующей записи цепочки ``table_name``.

    Под конкуренцией целостность цепочки одной таблицы обеспечивается per-table
    ``pg_advisory_xact_lock`` (детерминированный ключ от имени таблицы), взятым в
    той же транзакции ПЕРЕД чтением хвоста — это сериализует дописывание цепочки
    независимо от per-barrier lock ingestion. На не-postgres lock пропускается.

    Args:
        db: активная сессия (та же транзакция, что и вставка).
        table_name: имя append-only таблицы (только из ``_ALLOWED``).
        payload: значения строки БЕЗ hash-полей (``prev_hash``/``row_hash``).

    Raises:
        ValueError: если ``table_name`` не входит в allowlist append-only таблиц.
    """
    if table_name not in _ALLOWED:
        raise ValueError(f"hash-chain не разрешён для таблицы {table_name!r}")
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": _table_lock_key(table_name)},
        )
    prev_hash = db.execute(
        text(f"SELECT row_hash FROM {table_name} ORDER BY id DESC LIMIT 1")
    ).scalar()
    base = (prev_hash or "") + _canonical_json(payload)
    row_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return prev_hash, row_hash
