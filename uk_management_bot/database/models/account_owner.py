"""Владелец лицевого счёта по выгрузке Mening Uyim — снимок последней загрузки.

Квартира связана со счётом через ``apartments.account_number``; ФИО владельца
нужно только для подсказки менеджеру при проверке жителя
(``services/account_owners.py``). Каждая загрузка заменяет таблицу целиком.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base


class AccountOwner(Base):
    __tablename__ = "account_owners"

    account_number = Column(String(64), primary_key=True)
    owner_name = Column(String(255), nullable=False)
    imported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    imported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
