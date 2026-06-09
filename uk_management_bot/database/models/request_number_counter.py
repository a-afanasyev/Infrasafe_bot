"""Счётчик номеров заявок по дням (PR5, SSOT-кластер #1).

Единственный gap-safe источник суффикса номера YYMMDD-NNN: атомарный
UPSERT … RETURNING по строке дня. Заменяет три расходившиеся стратегии
(лексикографический MAX, COUNT(*)+1 в API/callcenter/inbound_alert) —
COUNT(*) переиспользовал номер после удаления строки, лексикографический
MAX ломался после 999 (`-1000` < `-999`).

Счётчик монотонен: удаление заявки с максимальным суффиксом НЕ приводит
к переиспользованию номера (self-seed из MAX(requests) выполняется только
при отсутствии строки дня).
"""

from sqlalchemy import Column, Integer, String

from uk_management_bot.database.session import Base


class RequestNumberCounter(Base):
    __tablename__ = "request_number_counters"

    # Префикс дня YYMMDD (бизнес-дата, Asia/Tashkent — см. request_number_service)
    day_prefix = Column(String(6), primary_key=True)
    # Последний выданный суффикс (последовательность начинается с 1)
    last_seq = Column(Integer, nullable=False)
