"""Ничьи заявки «В работе» без исполнителя → «Новая».

Инвариант (решение владельца 2026-08-17): «В работе» ⟺ у заявки есть
исполнитель. Групповое назначение больше не двигает статус — оно означает
«показать дежурным нужной специализации», а «В работе» наступает только когда
появился человек.

До этой правки групповая диспетчеризация уводила заявку в «В работе» с пустым
`executor_id`. Если никто из дежурных её не брал, она висела ничьей: на продах
так накопилось девять таких заявок (1 на profk с 8 августа, 8 на .105, старейшая
с 16 июня). Их и возвращаем в «Новую».

Что НЕ трогаем и почему:

* `assigned_group` / `assignment_type` / строку `request_assignments` — они
  сохраняются. Группа даёт дежурным ВИДИМОСТЬ заявки (`request_access`,
  `get_group_pool_query`) и теперь совместима со статусом «Новая»: именно так
  выглядит свежая заявка, которой не нашлось дежурного. Обнулив группу, мы
  спрятали бы эти девять заявок от исполнителей вместо того, чтобы вернуть их
  в оборот.
* Заявки «В работе» С исполнителем — их инвариант не нарушает.
* Заявки в других статусах — вне темы.

`updated_at` не выставляется вручную: у колонки `onupdate=func.now()`, и UPDATE
его подвинет сам. Это ожидаемо — строка действительно изменилась.

Идемпотентно: повторный прогон не найдёт строк (условие уже не выполняется).

Revision ID: 011
Revises: 010
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Канон-статусы литералами: миграция обязана быть воспроизводимой и не зависеть
# от текущего значения констант приложения.
_IN_PROGRESS = "В работе"
_NEW = "Новая"


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            "SELECT request_number FROM requests "
            "WHERE status = :in_progress AND executor_id IS NULL "
            "ORDER BY request_number"
        ),
        {"in_progress": _IN_PROGRESS},
    ).fetchall()

    if not rows:
        print("[011] ничьих заявок «В работе» не найдено — нечего возвращать")
        return

    numbers = [r[0] for r in rows]
    print(f"[011] возвращаю в «{_NEW}» {len(numbers)} ничьих заявок: "
          f"{', '.join(numbers)}")

    bind.execute(
        sa.text(
            "UPDATE requests SET status = :new "
            "WHERE status = :in_progress AND executor_id IS NULL"
        ),
        {"new": _NEW, "in_progress": _IN_PROGRESS},
    )


def downgrade() -> None:
    """No-op.

    Обратный UPDATE («Новая» без исполнителя → «В работе») задел бы ВСЕ новые
    заявки, а не только те девять: после отката отличить их уже нечем.
    Возвращать заявки в состояние, которое канон считает недопустимым, —
    заведомо хуже, чем оставить их в «Новой».
    """
