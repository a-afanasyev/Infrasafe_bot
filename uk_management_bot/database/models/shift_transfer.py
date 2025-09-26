from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from uk_management_bot.database.session import Base


class ShiftTransfer(Base):
    """Модель для передачи смен и заявок между исполнителями"""
    __tablename__ = "shift_transfers"

    id = Column(Integer, primary_key=True, index=True)

    # Основная информация о передаче
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False, index=True)
    from_executor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    to_executor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Статус передачи
    status = Column(String(50), nullable=False, default="pending", index=True)
    # pending - ожидает назначения исполнителя
    # assigned - назначен новый исполнитель
    # accepted - принято новым исполнителем
    # rejected - отклонено новым исполнителем
    # cancelled - отменено инициатором
    # completed - передача завершена

    # Причина передачи
    reason = Column(String(100), nullable=False, index=True)
    # illness - болезнь
    # emergency - экстренная ситуация
    # workload - перегрузка
    # vacation - отпуск
    # other - другое

    # Дополнительная информация
    comment = Column(Text, nullable=True)
    urgency_level = Column(String(20), nullable=False, default="normal")
    # low - низкий приоритет
    # normal - обычный приоритет
    # high - высокий приоритет
    # critical - критический приоритет

    # Временные метки
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    assigned_at = Column(DateTime, nullable=True, index=True)
    responded_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Системная информация
    auto_assigned = Column(Boolean, nullable=False, default=False)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)

    # Связи с другими моделями
    shift = relationship("Shift", back_populates="transfers")
    from_executor = relationship(
        "User",
        foreign_keys=[from_executor_id],
        back_populates="outgoing_transfers"
    )
    to_executor = relationship(
        "User",
        foreign_keys=[to_executor_id],
        back_populates="incoming_transfers"
    )

    def __repr__(self):
        return f"<ShiftTransfer(id={self.id}, shift_id={self.shift_id}, status='{self.status}')>"

    @property
    def is_pending(self) -> bool:
        """Проверяет, ожидает ли передача назначения исполнителя"""
        return self.status == "pending"

    @property
    def is_active(self) -> bool:
        """Проверяет, активна ли передача (не завершена и не отменена)"""
        return self.status in ["pending", "assigned", "accepted"]

    @property
    def can_retry(self) -> bool:
        """Проверяет, можно ли повторить попытку назначения"""
        return self.retry_count < self.max_retries

    @property
    def time_since_created(self) -> int:
        """Возвращает количество минут с момента создания"""
        if not self.created_at:
            return 0
        return int((datetime.utcnow() - self.created_at).total_seconds() / 60)

    def can_be_assigned_to(self, user_id: int) -> bool:
        """Проверяет, можно ли назначить передачу указанному пользователю"""
        # Нельзя назначить самому себе
        if user_id == self.from_executor_id:
            return False

        # Можно назначить только если статус pending
        return self.status == "pending"

    def update_status(self, new_status: str, comment: str = None) -> bool:
        """Обновляет статус передачи с валидацией переходов"""
        valid_transitions = {
            "pending": ["assigned", "cancelled"],
            "assigned": ["accepted", "rejected", "cancelled"],
            "accepted": ["completed", "cancelled"],
            "rejected": ["pending", "cancelled"],
            "cancelled": [],
            "completed": []
        }

        if new_status not in valid_transitions.get(self.status, []):
            return False

        old_status = self.status
        self.status = new_status

        # Обновляем временные метки
        now = datetime.utcnow()
        if new_status == "assigned":
            self.assigned_at = now
        elif new_status in ["accepted", "rejected"]:
            self.responded_at = now
        elif new_status == "completed":
            self.completed_at = now

        # Добавляем комментарий если предоставлен
        if comment:
            if self.comment:
                self.comment += f"\n[{now.strftime('%Y-%m-%d %H:%M')}] {comment}"
            else:
                self.comment = f"[{now.strftime('%Y-%m-%d %H:%M')}] {comment}"

        return True