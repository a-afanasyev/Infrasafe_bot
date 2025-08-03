# CREATIVE 2.2.1: ПРОЕКТИРОВАНИЕ ОБНОВЛЕНИЯ МОДЕЛИ USER

## 📋 ПРОБЛЕМА
Добавить поля для хранения предустановленных адресов пользователя в модель User и обновить связанные сервисы для поддержки выбора адресов в FSM создания заявок.

## 🎯 ТРЕБОВАНИЯ
- Добавить 4 новых поля в модель User для адресов
- Создать миграцию базы данных
- Обновить AuthService с методами для работы с адресами
- Создать утилиты для валидации и форматирования адресов
- Обеспечить обратную совместимость
- Поддержать валидацию и логирование

## 🔍 АНАЛИЗ ВАРИАНТОВ

### 1. МОДЕЛЬ USER - ВАРИАНТЫ АРХИТЕКТУРЫ

#### Вариант A: Прямые поля в модели User
**Описание**: Добавить поля `home_address`, `apartment_address`, `yard_address`, `address_type` напрямую в модель User.

**Плюсы**:
- ✅ Простота реализации
- ✅ Высокая производительность запросов
- ✅ Простота миграции
- ✅ Понятность для разработчиков
- ✅ Соответствует текущей архитектуре

**Минусы**:
- ❌ Менее гибко для будущих расширений
- ❌ Ограниченное количество типов адресов

**Оценка**: ⭐⭐⭐⭐⭐ (5/5) - оптимально для текущих требований

#### Вариант B: Отдельная модель UserAddress
**Описание**: Создать отдельную модель UserAddress с связью один-ко-многим с User.

**Плюсы**:
- ✅ Высокая гибкость
- ✅ Неограниченное количество адресов
- ✅ Легкое добавление новых типов адресов

**Минусы**:
- ❌ Избыточная сложность для текущих требований
- ❌ Сложность миграции
- ❌ Дополнительные запросы к БД
- ❌ Усложнение кода

**Оценка**: ⭐⭐ (2/5) - избыточно для текущих требований

#### Вариант C: JSON поле для адресов
**Описание**: Использовать JSON поле для хранения всех адресов пользователя.

**Плюсы**:
- ✅ Гибкость структуры
- ✅ Простота добавления новых типов

**Минусы**:
- ❌ Сложность валидации
- ❌ Сложность запросов
- ❌ Проблемы с индексацией
- ❌ Сложность миграции

**Оценка**: ⭐⭐ (2/5) - не подходит для текущих требований

### 2. МИГРАЦИЯ БАЗЫ ДАННЫХ - ВАРИАНТЫ

#### Вариант A: Простая миграция с ALTER TABLE
**Описание**: Использовать простые ALTER TABLE команды для добавления новых колонок.

**Плюсы**:
- ✅ Простота реализации
- ✅ Быстрое выполнение
- ✅ Минимальный риск
- ✅ Легкость отката

**Минусы**:
- ❌ Ограниченная гибкость

**Оценка**: ⭐⭐⭐⭐⭐ (5/5) - оптимально для текущих требований

#### Вариант B: Создание новой таблицы
**Описание**: Создать новую таблицу и перенести данные.

**Плюсы**:
- ✅ Возможность сложных преобразований

**Минусы**:
- ❌ Избыточная сложность
- ❌ Высокий риск
- ❌ Долгое выполнение

**Оценка**: ⭐ (1/5) - избыточно

#### Вариант C: Поэтапная миграция
**Описание**: Разбить миграцию на несколько этапов с проверками.

**Плюсы**:
- ✅ Безопасность
- ✅ Возможность отката на каждом этапе

**Минусы**:
- ❌ Избыточная сложность для простой задачи
- ❌ Долгое выполнение

**Оценка**: ⭐⭐ (2/5) - избыточно для простой задачи

### 3. AUTHSERVICE - ВАРИАНТЫ АРХИТЕКТУРЫ

#### Вариант A: Добавить методы в существующий AuthService
**Описание**: Расширить существующий AuthService новыми методами для работы с адресами.

**Плюсы**:
- ✅ Простота реализации
- ✅ Логичность (адреса - часть профиля пользователя)
- ✅ Соответствует текущей архитектуре
- ✅ Минимальные изменения

**Минусы**:
- ❌ Увеличение размера AuthService

**Оценка**: ⭐⭐⭐⭐⭐ (5/5) - оптимально для текущих требований

#### Вариант B: Создать отдельный AddressService
**Описание**: Создать отдельный сервис для работы с адресами.

**Плюсы**:
- ✅ Разделение ответственности
- ✅ Возможность переиспользования

**Минусы**:
- ❌ Избыточная сложность
- ❌ Дополнительные зависимости
- ❌ Усложнение архитектуры

**Оценка**: ⭐⭐ (2/5) - избыточно для текущих требований

#### Вариант C: Использовать миксины
**Описание**: Создать миксин для функциональности адресов.

**Плюсы**:
- ✅ Переиспользование кода
- ✅ Модульность

**Минусы**:
- ❌ Избыточная сложность
- ❌ Усложнение понимания кода
- ❌ Не соответствует текущей архитектуре

**Оценка**: ⭐⭐ (2/5) - избыточно для текущих требований

## 🏆 РЕШЕНИЕ

### Выбранная архитектура:

#### 1. Модель User - Вариант A: Прямые поля
```python
class User(Base):
    __tablename__ = "users"
    
    # Существующие поля...
    
    # Новые поля для адресов
    home_address = Column(Text, nullable=True)
    apartment_address = Column(Text, nullable=True)
    yard_address = Column(Text, nullable=True)
    address_type = Column(String(20), nullable=True)  # home/apartment/yard
```

#### 2. Миграция - Вариант A: Простая миграция
```sql
-- Миграция для добавления полей адресов
ALTER TABLE users ADD COLUMN home_address TEXT;
ALTER TABLE users ADD COLUMN apartment_address TEXT;
ALTER TABLE users ADD COLUMN yard_address TEXT;
ALTER TABLE users ADD COLUMN address_type VARCHAR(20);

-- Обновление существующих данных (опционально)
UPDATE users SET address_type = 'home' WHERE address IS NOT NULL;
```

#### 3. AuthService - Вариант A: Расширение существующего сервиса
```python
class AuthService:
    # Существующие методы...
    
    async def get_user_addresses(self, user_id: int) -> dict:
        """Получить все адреса пользователя"""
        
    async def update_user_address(self, user_id: int, address_type: str, address: str) -> bool:
        """Обновить адрес пользователя по типу"""
        
    async def get_user_address_by_type(self, user_id: int, address_type: str) -> str:
        """Получить адрес пользователя по типу"""
```

## 🏗️ ТЕХНИЧЕСКАЯ АРХИТЕКТУРА

### 1. Обновленная модель User
```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database.session import Base

class User(Base):
    __tablename__ = "users"
    
    # Существующие поля
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    role = Column(String(50), default="applicant", nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    language = Column(String(10), default="ru", nullable=False)
    phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)  # Существующее поле (оставляем для совместимости)
    
    # Новые поля для адресов
    home_address = Column(Text, nullable=True)
    apartment_address = Column(Text, nullable=True)
    yard_address = Column(Text, nullable=True)
    address_type = Column(String(20), nullable=True)  # home/apartment/yard
    
    # Системные поля
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Обратные связи
    requests = relationship("Request", back_populates="user", foreign_keys="Request.user_id")
    shifts = relationship("Shift", back_populates="user")
    executed_requests = relationship("Request", foreign_keys="Request.executor_id")
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, role={self.role}, status={self.status}, address_type={self.address_type})>"
```

### 2. Миграция базы данных
```python
# database/migrations/add_user_addresses.py
import sqlite3
import logging

logger = logging.getLogger(__name__)

def migrate_add_user_addresses(db_path: str):
    """Миграция для добавления полей адресов в таблицу users"""
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Добавляем новые колонки
        cursor.execute("ALTER TABLE users ADD COLUMN home_address TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN apartment_address TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN yard_address TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN address_type VARCHAR(20)")
        
        # Обновляем существующие данные (опционально)
        cursor.execute("UPDATE users SET address_type = 'home' WHERE address IS NOT NULL")
        
        conn.commit()
        logger.info("Миграция add_user_addresses выполнена успешно")
        
    except Exception as e:
        logger.error(f"Ошибка миграции add_user_addresses: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def rollback_add_user_addresses(db_path: str):
    """Откат миграции add_user_addresses"""
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Удаляем новые колонки (SQLite не поддерживает DROP COLUMN)
        # Создаем новую таблицу без новых колонок
        cursor.execute("""
            CREATE TABLE users_backup AS 
            SELECT id, telegram_id, username, first_name, last_name, 
                   role, status, language, phone, address, 
                   created_at, updated_at 
            FROM users
        """)
        
        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_backup RENAME TO users")
        
        conn.commit()
        logger.info("Откат миграции add_user_addresses выполнен успешно")
        
    except Exception as e:
        logger.error(f"Ошибка отката миграции add_user_addresses: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
```

### 3. Обновленный AuthService
```python
# services/auth_service.py
import logging
from sqlalchemy.orm import Session
from database.models import User
from utils.constants import ADDRESS_TYPES, MAX_ADDRESS_LENGTH
from utils.address_helpers import validate_address, format_address

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    
    # Существующие методы...
    
    async def get_user_addresses(self, user_id: int) -> dict:
        """Получить все адреса пользователя"""
        try:
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return {}
            
            addresses = {}
            if user.home_address:
                addresses['home'] = user.home_address
            if user.apartment_address:
                addresses['apartment'] = user.apartment_address
            if user.yard_address:
                addresses['yard'] = user.yard_address
            
            return addresses
            
        except Exception as e:
            logger.error(f"Ошибка получения адресов пользователя {user_id}: {e}")
            return {}
    
    async def update_user_address(self, user_id: int, address_type: str, address: str) -> bool:
        """Обновить адрес пользователя по типу"""
        try:
            if address_type not in ADDRESS_TYPES:
                logger.warning(f"Неверный тип адреса: {address_type}")
                return False
            
            if not validate_address(address):
                logger.warning(f"Неверный адрес: {address}")
                return False
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден")
                return False
            
            # Обновляем соответствующее поле
            if address_type == 'home':
                user.home_address = format_address(address)
            elif address_type == 'apartment':
                user.apartment_address = format_address(address)
            elif address_type == 'yard':
                user.yard_address = format_address(address)
            
            self.db.commit()
            logger.info(f"Адрес пользователя {user_id} обновлен: {address_type} = {address}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления адреса пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    async def get_user_address_by_type(self, user_id: int, address_type: str) -> str:
        """Получить адрес пользователя по типу"""
        try:
            if address_type not in ADDRESS_TYPES:
                return None
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return None
            
            if address_type == 'home':
                return user.home_address
            elif address_type == 'apartment':
                return user.apartment_address
            elif address_type == 'yard':
                return user.yard_address
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения адреса пользователя {user_id}: {e}")
            return None
    
    async def get_available_addresses(self, user_id: int) -> dict:
        """Получить доступные адреса пользователя для FSM"""
        try:
            addresses = await self.get_user_addresses(user_id)
            available = {}
            
            for addr_type, address in addresses.items():
                if address and len(address.strip()) >= 10:  # Минимум 10 символов
                    available[addr_type] = address
            
            return available
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных адресов пользователя {user_id}: {e}")
            return {}
```

### 4. Утилиты для работы с адресами
```python
# utils/address_helpers.py
import re
from typing import Optional
from utils.constants import MAX_ADDRESS_LENGTH, ADDRESS_TYPES

def validate_address(address: str) -> bool:
    """Валидация адреса"""
    if not address or not isinstance(address, str):
        return False
    
    # Проверяем длину
    if len(address.strip()) < 10:
        return False
    
    if len(address) > MAX_ADDRESS_LENGTH:
        return False
    
    # Проверяем на наличие недопустимых символов
    if re.search(r'[<>"\']', address):
        return False
    
    return True

def format_address(address: str) -> str:
    """Форматирование адреса"""
    if not address:
        return ""
    
    # Убираем лишние пробелы
    formatted = re.sub(r'\s+', ' ', address.strip())
    
    # Первая буква заглавная
    formatted = formatted.capitalize()
    
    return formatted

def get_address_type_display(address_type: str) -> str:
    """Получить отображаемое название типа адреса"""
    displays = {
        'home': '🏠 Мой дом',
        'apartment': '🏢 Моя квартира',
        'yard': '🌳 Мой двор'
    }
    return displays.get(address_type, address_type)

def get_available_addresses(user) -> dict:
    """Получить доступные адреса пользователя"""
    available = {}
    
    if user.home_address and validate_address(user.home_address):
        available['home'] = user.home_address
    
    if user.apartment_address and validate_address(user.apartment_address):
        available['apartment'] = user.apartment_address
    
    if user.yard_address and validate_address(user.yard_address):
        available['yard'] = user.yard_address
    
    return available
```

### 5. Обновленные константы
```python
# utils/constants.py
# Добавить к существующим константам:

# Типы адресов пользователя
ADDRESS_TYPE_HOME = "home"
ADDRESS_TYPE_APARTMENT = "apartment"
ADDRESS_TYPE_YARD = "yard"

ADDRESS_TYPES = [ADDRESS_TYPE_HOME, ADDRESS_TYPE_APARTMENT, ADDRESS_TYPE_YARD]

# Максимальная длина адреса
MAX_ADDRESS_LENGTH = 500

# Отображаемые названия типов адресов
ADDRESS_TYPE_DISPLAYS = {
    ADDRESS_TYPE_HOME: "🏠 Мой дом",
    ADDRESS_TYPE_APARTMENT: "🏢 Моя квартира",
    ADDRESS_TYPE_YARD: "🌳 Мой двор"
}
```

## ✅ КРИТЕРИИ УСПЕХА

### Функциональные требования:
- [ ] Новые поля добавлены в модель User
- [ ] Миграция базы данных создана и протестирована
- [ ] AuthService обновлен с новыми методами
- [ ] Утилиты для работы с адресами созданы
- [ ] Константы обновлены
- [ ] Обратная совместимость сохранена

### Технические требования:
- [ ] Валидация адресов работает корректно
- [ ] Форматирование адресов работает корректно
- [ ] Логирование операций с адресами
- [ ] Обработка ошибок при работе с адресами
- [ ] Производительность запросов не ухудшилась

### Тестирование:
- [ ] Создание пользователя с адресами
- [ ] Обновление адресов пользователя
- [ ] Получение адресов по типу
- [ ] Валидация некорректных адресов
- [ ] Миграция базы данных
- [ ] Откат миграции

## ⏱️ ПЛАН РЕАЛИЗАЦИИ

### День 1 (1 день):
- **Утро**: Обновление модели User и констант
- **День**: Создание миграции и утилит
- **Вечер**: Обновление AuthService и тестирование

### Файлы для создания/обновления:
1. `database/models/user.py` - обновление модели
2. `database/migrations/add_user_addresses.py` - миграция
3. `services/auth_service.py` - новые методы
4. `utils/address_helpers.py` - утилиты
5. `utils/constants.py` - новые константы

## 🎯 РЕЗУЛЬТАТ
Детальное проектирование архитектуры обновления модели User завершено. Выбрана оптимальная архитектура с прямыми полями в модели User, простой миграцией и расширением AuthService. Все компоненты спроектированы с учетом производительности, простоты и обратной совместимости. 