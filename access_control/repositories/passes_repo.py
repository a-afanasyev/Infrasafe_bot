"""Доступ к ``access_passes``: атомарный расход въезда временного пропуска (§10.3)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.enums import PassStatus


def consume_taxi_entry(db: Session, pass_id: int) -> bool:
    """Атомарно израсходовать один въезд taxi-pass (§10.3).

    ``UPDATE ... SET used_entries = used_entries + 1 WHERE id = :p AND
    used_entries < max_entries``. Возвращает True при успехе (выделена ёмкость),
    False — если лимит уже исчерпан. При достижении max — статус 'used'.
    """
    updated = db.execute(
        text(
            "UPDATE access_passes "
            "SET used_entries = used_entries + 1, "
            "    status = CASE WHEN used_entries + 1 >= max_entries "
            "                  THEN :used ELSE status END "
            "WHERE id = :p AND used_entries < max_entries"
        ),
        {"p": pass_id, "used": PassStatus.USED.value},
    )
    return updated.rowcount == 1
