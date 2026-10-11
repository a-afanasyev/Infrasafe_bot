"""Админка ролей: роли и их права, которые суперадмин меняет из веба.

Действия (что вообще можно проверить) живут в коде — `authz/catalog.py`.
Здесь хранится только то, что настраивается без релиза:

* `RbacRole` — роль: системная (8 ролей «из коробки», удалить нельзя) или
  созданная админом.
* `RbacRolePermission` — явное «разрешено / запрещено» для пары
  (роль, действие). Пары без строки берут значение по умолчанию из каталога —
  так новое действие из кода сразу работает с правами «из коробки».
* `RbacState` — одна строка со счётчиком версий. Каждое изменение прав
  увеличивает его; процессы API/бота/охраны перечитывают права, увидев новую
  версию (`authz/store.py`).
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import false as sql_false, func

from uk_management_bot.database.session import Base


class RbacRole(Base):
    __tablename__ = "rbac_roles"

    key = Column(String(32), primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False, server_default=sql_false())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<RbacRole(key={self.key!r}, system={self.is_system})>"


class RbacRolePermission(Base):
    __tablename__ = "rbac_role_permissions"

    role_key = Column(String(32), ForeignKey("rbac_roles.key", ondelete="CASCADE"), primary_key=True)
    action_key = Column(String(64), primary_key=True)
    allowed = Column(Boolean, nullable=False)

    def __repr__(self):
        return f"<RbacRolePermission({self.role_key!r}, {self.action_key!r}, allowed={self.allowed})>"


class RbacState(Base):
    __tablename__ = "rbac_state"

    id = Column(Integer, primary_key=True)
    version = Column(BigInteger, nullable=False, default=0, server_default="0")
