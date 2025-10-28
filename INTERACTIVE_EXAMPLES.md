# 🎮 Интерактивные примеры UK Management Bot API

**Версия**: 2.1.0
**Дата**: 27.10.2025

> Эти примеры можно копировать и выполнять в вашем окружении

---

## 📋 Содержание

1. [Настройка окружения](#настройка-окружения)
2. [Работа с пользователями](#работа-с-пользователями)
3. [Управление заявками](#управление-заявками)
4. [Работа с адресами](#работа-с-адресами)
5. [Система смен](#система-смен)
6. [AI-powered назначения](#ai-powered-назначения)

---

## 🔧 Настройка окружения

### Установка зависимостей

```bash
# Активируйте виртуальное окружение
cd /path/to/uk-management-bot
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

### Запуск в Docker

```bash
# Запуск всех сервисов
docker-compose -f docker-compose.dev.yml up -d

# Проверка статуса
docker-compose -f docker-compose.dev.yml ps

# Просмотр логов
docker-compose -f docker-compose.dev.yml logs -f app
```

### Подключение к базе данных

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uk_management_bot.config.settings import settings

# Создаем engine
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Получаем сессию
db = SessionLocal()

# Не забудьте закрыть сессию после использования
try:
    # Ваш код здесь
    pass
finally:
    db.close()
```

---

## 👤 Работа с пользователями

### Пример 1: Создание и одобрение пользователя

```python
import asyncio
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.database.models import User

async def create_and_approve_user_example():
    """Полный цикл: создание → одобрение → назначение роли"""

    # Инициализация сервиса
    auth = AuthService(db)

    # 1. Создание нового пользователя
    print("🔹 Создание пользователя...")
    user = await auth.get_or_create_user(
        telegram_id=987654321,
        username="new_executor",
        first_name="Иван",
        last_name="Петров"
    )
    print(f"✅ Создан пользователь: {user.first_name} {user.last_name}")
    print(f"   Статус: {user.status}")  # pending
    print(f"   Роль: {user.role}")      # applicant

    # 2. Одобрение пользователя менеджером
    print("\n🔹 Одобрение пользователя...")
    success = await auth.approve_user(
        telegram_id=987654321,
        role="executor"  # Назначаем роль исполнителя
    )

    if success:
        print("✅ Пользователь одобрен!")
        # Обновляем данные
        user = await auth.get_user_by_telegram_id(987654321)
        print(f"   Новый статус: {user.status}")     # approved
        print(f"   Новая роль: {user.active_role}")  # executor

    # 3. Проверка прав
    print("\n🔹 Проверка прав...")
    is_executor = await auth.is_user_executor(987654321)
    is_manager = await auth.is_user_manager(987654321)
    print(f"   Является исполнителем: {is_executor}")  # True
    print(f"   Является менеджером: {is_manager}")      # False

# Запуск примера
asyncio.run(create_and_approve_user_example())
```

**Ожидаемый вывод**:
```
🔹 Создание пользователя...
✅ Создан пользователь: Иван Петров
   Статус: pending
   Роль: applicant

🔹 Одобрение пользователя...
✅ Пользователь одобрен!
   Новый статус: approved
   Новая роль: executor

🔹 Проверка прав...
   Является исполнителем: True
   Является менеджером: False
```

---

### Пример 2: Переключение ролей с rate limiting

```python
async def role_switching_example():
    """Демонстрация переключения ролей с проверкой rate limit"""

    auth = AuthService(db)
    telegram_id = 123456789

    print("🔹 Попытка быстрого переключения ролей...")

    # Первое переключение - успех
    success1, reason1 = await auth.try_set_active_role_with_rate_limit(
        telegram_id=telegram_id,
        role="executor",
        window_seconds=10
    )
    print(f"Переключение 1: {'✅ Успех' if success1 else f'❌ Ошибка: {reason1}'}")

    # Немедленное повторное переключение - rate limit
    success2, reason2 = await auth.try_set_active_role_with_rate_limit(
        telegram_id=telegram_id,
        role="manager",
        window_seconds=10
    )
    print(f"Переключение 2: {'✅ Успех' if success2 else f'❌ Ошибка: {reason2}'}")

    # Ждем 10 секунд
    print("\n⏳ Ожидание 10 секунд...")
    await asyncio.sleep(10)

    # Повторная попытка - успех
    success3, reason3 = await auth.try_set_active_role_with_rate_limit(
        telegram_id=telegram_id,
        role="manager",
        window_seconds=10
    )
    print(f"Переключение 3: {'✅ Успех' if success3 else f'❌ Ошибка: {reason3}'}")

asyncio.run(role_switching_example())
```

**Ожидаемый вывод**:
```
🔹 Попытка быстрого переключения ролей...
Переключение 1: ✅ Успех
Переключение 2: ❌ Ошибка: rate_limited

⏳ Ожидание 10 секунд...
Переключение 3: ✅ Успех
```

---

## 📝 Управление заявками

### Пример 3: Создание заявки с автоматическим номером

```python
from uk_management_bot.services.async_request_service import AsyncRequestService
from uk_management_bot.services.request_number_service import RequestNumberService

async def create_request_example():
    """Создание заявки с демонстрацией Request Number System"""

    request_service = AsyncRequestService(db)

    print("🔹 Создание новой заявки...")

    # Создаем заявку
    new_request = await request_service.create_request(
        user_id=123,
        category="сантехника",
        address="ул. Примерная, д.1, кв.10",
        description="Течет кран на кухне",
        urgency="срочная"
    )

    print(f"✅ Заявка создана!")
    print(f"   Номер: {new_request.request_number}")  # Например: 251027-042
    print(f"   Категория: {new_request.category}")
    print(f"   Статус: {new_request.status}")
    print(f"   Срочность: {new_request.urgency}")

    # Разбор номера заявки
    print("\n🔹 Анализ номера заявки...")
    parsed = RequestNumberService.parse_request_number(new_request.request_number)

    if parsed["valid"]:
        print(f"   Дата создания: {parsed['date'].strftime('%d.%m.%Y')}")
        print(f"   Порядковый номер дня: {parsed['sequence']}")

    # Форматирование для отображения
    display_format = RequestNumberService.format_for_display(new_request.request_number)
    print(f"   Для отображения: {display_format}")

    return new_request

asyncio.run(create_request_example())
```

**Ожидаемый вывод**:
```
🔹 Создание новой заявки...
✅ Заявка создана!
   Номер: 251027-042
   Категория: сантехника
   Статус: новая
   Срочность: срочная

🔹 Анализ номера заявки...
   Дата создания: 27.10.2025
   Порядковый номер дня: 42
   Для отображения: №251027-042 (27.10.2025)
```

---

### Пример 4: Полный жизненный цикл заявки

```python
async def request_lifecycle_example():
    """Полный жизненный цикл: создание → назначение → выполнение → завершение"""

    request_service = AsyncRequestService(db)

    # 1. Создание
    print("📝 Шаг 1: Создание заявки")
    request = await request_service.create_request(
        user_id=123,
        category="электрика",
        address="ул. Ленина, д.5, кв.23",
        description="Не работает розетка в спальне",
        urgency="обычная"
    )
    print(f"   ✅ Создана: {request.request_number}")

    # 2. Назначение исполнителю
    print("\n👷 Шаг 2: Назначение исполнителю")
    await request_service.assign_request_to_executor(
        request_number=request.request_number,
        executor_id=456,
        assigner_id=789
    )
    print(f"   ✅ Назначена исполнителю ID: 456")

    # 3. Начало работы
    print("\n🔧 Шаг 3: Исполнитель начинает работу")
    await request_service.update_request_status(
        request_number=request.request_number,
        status="в_работе",
        user_id=456,
        notes="Выехал на объект, начинаю диагностику",
        notify=True
    )
    print(f"   ✅ Статус: в_работе")

    # 4. Завершение
    print("\n✅ Шаг 4: Завершение работы")
    await request_service.update_request_status(
        request_number=request.request_number,
        status="выполнена",
        user_id=456,
        notes="Заменена неисправная розетка, проверена проводка",
        notify=True
    )
    print(f"   ✅ Статус: выполнена")

    # 5. Проверка истории
    print("\n📊 Шаг 5: История заявки")
    updated_request = await request_service.get_request_by_number(request.request_number)
    print(f"   Статус: {updated_request.status}")
    print(f"   Заметки: {updated_request.notes}")

asyncio.run(request_lifecycle_example())
```

**Ожидаемый вывод**:
```
📝 Шаг 1: Создание заявки
   ✅ Создана: 251027-043

👷 Шаг 2: Назначение исполнителю
   ✅ Назначена исполнителю ID: 456

🔧 Шаг 3: Исполнитель начинает работу
   ✅ Статус: в_работе

✅ Шаг 4: Завершение работы
   ✅ Статус: выполнена

📊 Шаг 5: История заявки
   Статус: выполнена
   Заметки: Заменена неисправная розетка, проверена проводка
```

---

## 🏘️ Работа с адресами

### Пример 5: Создание иерархии адресов

```python
from uk_management_bot.services.address_service import AddressService

async def create_address_hierarchy_example():
    """Создание полной иерархии: Двор → Здание → Квартиры"""

    # 1. Создание двора
    print("🏞️  Шаг 1: Создание двора")
    yard, error = await AddressService.create_yard(
        session=db,
        name="Микрорайон \"Северный\"",
        created_by=1,
        description="Жилой комплекс из 3 зданий",
        gps_latitude=41.311151,
        gps_longitude=69.279737
    )

    if yard:
        print(f"   ✅ Создан двор ID: {yard.id}")
    else:
        print(f"   ❌ Ошибка: {error}")
        return

    # 2. Создание здания
    print("\n🏢 Шаг 2: Создание здания")
    building, error = await AddressService.create_building(
        session=db,
        address="ул. Пушкина, д. 10",
        yard_id=yard.id,
        created_by=1,
        entrance_count=3,
        floor_count=9,
        description="9-этажный жилой дом"
    )

    if building:
        print(f"   ✅ Создано здание ID: {building.id}")
    else:
        print(f"   ❌ Ошибка: {error}")
        return

    # 3. Массовое создание квартир
    print("\n🏠 Шаг 3: Создание квартир")
    apartment_numbers = [f"{i}" for i in range(1, 28)]  # Квартиры 1-27

    result = await AddressService.bulk_create_apartments(
        session=db,
        building_id=building.id,
        apartment_numbers=apartment_numbers,
        created_by=1,
        floor=1,  # Первый этаж
        entrance=1
    )

    print(f"   ✅ Создано квартир: {result['created_count']}")
    if result['failed']:
        print(f"   ⚠️  Не удалось создать: {len(result['failed'])}")

    # 4. Поиск квартир
    print("\n🔍 Шаг 4: Поиск квартир")
    apartments = await AddressService.search_apartments(
        session=db,
        building_id=building.id,
        limit=5
    )

    print(f"   Найдено квартир: {len(apartments)}")
    for apt in apartments[:3]:
        print(f"   - Квартира №{apt.apartment_number}, этаж: {apt.floor}")

asyncio.run(create_address_hierarchy_example())
```

**Ожидаемый вывод**:
```
🏞️  Шаг 1: Создание двора
   ✅ Создан двор ID: 1

🏢 Шаг 2: Создание здания
   ✅ Создано здание ID: 1

🏠 Шаг 3: Создание квартир
   ✅ Создано квартир: 27

🔍 Шаг 4: Поиск квартир
   Найдено квартир: 27
   - Квартира №1, этаж: 1
   - Квартира №2, этаж: 1
   - Квартира №3, этаж: 1
```

---

### Пример 6: Модерация запросов на квартиры

```python
async def apartment_moderation_example():
    """Процесс модерации запросов на добавление квартир"""

    user_telegram_id = 123456789
    manager_id = 1

    # 1. Пользователь запрашивает доступ к квартире
    print("📋 Шаг 1: Запрос доступа к квартире")
    user_apartment, error = await AddressService.request_apartment(
        session=db,
        user_telegram_id=user_telegram_id,
        apartment_id=5,
        justification="Я собственник этой квартиры"
    )

    if user_apartment:
        print(f"   ✅ Запрос создан ID: {user_apartment.id}")
        print(f"   Статус: {user_apartment.status}")  # pending

    # 2. Менеджер просматривает запросы
    print("\n👀 Шаг 2: Менеджер проверяет ожидающие запросы")
    pending = await AddressService.get_pending_requests(session=db, limit=10)
    print(f"   Найдено запросов: {len(pending)}")

    # 3. Менеджер одобряет запрос
    print("\n✅ Шаг 3: Одобрение запроса")
    success, error = await AddressService.approve_apartment_request(
        session=db,
        request_id=user_apartment.id,
        approved_by=manager_id
    )

    if success:
        print("   ✅ Запрос одобрен!")

        # Проверяем квартиры пользователя
        user_apts = await AddressService.get_user_apartments(
            session=db,
            user_telegram_id=user_telegram_id,
            only_approved=True
        )
        print(f"   Пользователь теперь привязан к {len(user_apts)} квартире(ам)")

asyncio.run(apartment_moderation_example())
```

**Ожидаемый вывод**:
```
📋 Шаг 1: Запрос доступа к квартире
   ✅ Запрос создан ID: 1
   Статус: pending

👀 Шаг 2: Менеджер проверяет ожидающие запросы
   Найдено запросов: 1

✅ Шаг 3: Одобрение запроса
   ✅ Запрос одобрен!
   Пользователь теперь привязан к 1 квартире(ам)
```

---

## ⏰ Система смен

### Пример 7: Передача смен с заявками

```python
from uk_management_bot.services.shift_transfer_service import ShiftTransferService

async def shift_transfer_example():
    """Полный процесс передачи заявок между сменами"""

    transfer_service = ShiftTransferService(db)

    # 1. Инициация передачи
    print("🔄 Шаг 1: Инициация передачи между сменами")
    transfer = transfer_service.initiate_shift_transfer(
        outgoing_shift_id=10,  # Завершающаяся смена
        incoming_shift_id=11,  # Начинающаяся смена
        initiated_by=1  # Менеджер
    )

    if transfer:
        print(f"   ✅ Передача инициирована")
        print(f"   Статус: {transfer.status.value}")
        print(f"   Заявок к передаче: {transfer.total_requests}")
    else:
        print("   ❌ Не удалось инициировать передачу")
        return

    # 2. Начало процесса передачи
    print("\n▶️  Шаг 2: Начало процесса передачи")
    success = transfer_service.start_transfer_process(
        transfer=transfer,
        executor_id=456  # Исполнитель входящей смены
    )

    if success:
        print(f"   ✅ Процесс начат")
        print(f"   Статус: IN_PROGRESS")

    # 3. Завершение передачи
    print("\n✅ Шаг 3: Завершение передачи")
    success = transfer_service.complete_transfer(
        transfer=transfer,
        executor_id=456,
        completion_notes="Все заявки приняты, начинаю работу"
    )

    if success:
        print(f"   ✅ Передача завершена")
        print(f"   Передано заявок: {transfer.transferred_requests}")
        print(f"   Ошибок: {transfer.failed_requests}")

    # 4. Статистика передач
    print("\n📊 Шаг 4: Статистика передач за месяц")
    stats = transfer_service.get_transfer_statistics(days=30)
    print(f"   Всего передач: {stats.get('total_transfers', 0)}")
    print(f"   Успешных: {stats.get('completed_transfers', 0)}")

asyncio.run(shift_transfer_example())
```

**Ожидаемый вывод**:
```
🔄 Шаг 1: Инициация передачи между сменами
   ✅ Передача инициирована
   Статус: pending
   Заявок к передаче: 5

▶️  Шаг 2: Начало процесса передачи
   ✅ Процесс начат
   Статус: IN_PROGRESS

✅ Шаг 3: Завершение передачи
   ✅ Передача завершена
   Передано заявок: 5
   Ошибок: 0

📊 Шаг 4: Статистика передач за месяц
   Всего передач: 12
   Успешных: 11
```

---

## 🤖 AI-powered назначения

### Пример 8: Умное назначение с AI

```python
from uk_management_bot.services.async_smart_dispatcher import AsyncSmartDispatcher

async def smart_assignment_example():
    """Демонстрация AI-powered назначения заявок"""

    # Создаем заявку
    request_service = AsyncRequestService(db)
    request = await request_service.create_request(
        user_id=123,
        category="сантехника",
        address="ул. Навои, д.15, кв.42",
        description="Засорилась канализация",
        urgency="срочная"
    )

    print(f"📝 Создана заявка: {request.request_number}")
    print(f"   Категория: {request.category}")
    print(f"   Срочность: {request.urgency}")

    # Используем AI для назначения
    print("\n🤖 Запуск AI-назначения...")
    dispatcher = AsyncSmartDispatcher(db)

    result = await dispatcher.smart_assign(
        request_number=request.request_number,
        user_id=1  # ID менеджера
    )

    if result["success"]:
        print(f"   ✅ Заявка назначена!")
        print(f"   Исполнитель ID: {result['executor_id']}")
        print(f"   Оценка соответствия: {result['score']:.2f}")
        print(f"   Обоснование: {result['reasoning']}")
    else:
        print(f"   ❌ Не удалось назначить: {result.get('error')}")

    # Получение оценок всех исполнителей
    print("\n📊 Оценки всех доступных исполнителей:")
    scores = await dispatcher.score_executors(request)

    for idx, executor_score in enumerate(scores[:5], 1):
        print(f"   {idx}. Исполнитель ID {executor_score['executor_id']}: "
              f"{executor_score['score']:.2f} баллов")
        print(f"      Специализация: {executor_score.get('specialization')}")
        print(f"      Расстояние: {executor_score.get('distance_km', 'N/A')} км")
        print(f"      Загрузка: {executor_score.get('workload', 0)} заявок")

asyncio.run(smart_assignment_example())
```

**Ожидаемый вывод**:
```
📝 Создана заявка: 251027-044
   Категория: сантехника
   Срочность: срочная

🤖 Запуск AI-назначения...
   ✅ Заявка назначена!
   Исполнитель ID: 456
   Оценка соответствия: 0.89
   Обоснование: Лучший выбор: специализация совпадает (0.35), близкое расположение (0.25), низкая загрузка (0.20), высокий рейтинг (0.15)

📊 Оценки всех доступных исполнителей:
   1. Исполнитель ID 456: 0.89 баллов
      Специализация: сантехник
      Расстояние: 1.2 км
      Загрузка: 2 заявок
   2. Исполнитель ID 789: 0.76 баллов
      Специализация: сантехник
      Расстояние: 3.5 км
      Загрузка: 4 заявок
   3. Исполнитель ID 234: 0.64 баллов
      Специализация: универсал
      Расстояние: 0.8 км
      Загрузка: 6 заявок
```

---

## 🧪 Тестирование в pytest

### Пример 9: Unit-тесты для сервисов

```python
import pytest
from uk_management_bot.services.request_number_service import RequestNumberService
from datetime import date

def test_generate_request_number():
    """Тест генерации номера заявки"""
    # Генерируем номер для конкретной даты
    test_date = date(2025, 10, 27)
    number = RequestNumberService.generate_next_number(
        creation_date=test_date,
        db=None  # Для теста без БД
    )

    # Проверяем формат
    assert number == "251027-001"

def test_validate_request_number():
    """Тест валидации формата"""
    # Валидные номера
    assert RequestNumberService.validate_request_number_format("251027-001") == True
    assert RequestNumberService.validate_request_number_format("250101-999") == True

    # Невалидные номера
    assert RequestNumberService.validate_request_number_format("251027-1") == False
    assert RequestNumberService.validate_request_number_format("2510271001") == False
    assert RequestNumberService.validate_request_number_format("25-10-27-001") == False

def test_parse_request_number():
    """Тест парсинга номера"""
    parsed = RequestNumberService.parse_request_number("251027-042")

    assert parsed["valid"] == True
    assert parsed["year"] == 2025
    assert parsed["month"] == 10
    assert parsed["day"] == 27
    assert parsed["sequence"] == 42

@pytest.mark.asyncio
async def test_create_request(db_session):
    """Интеграционный тест создания заявки"""
    from uk_management_bot.services.async_request_service import AsyncRequestService

    service = AsyncRequestService(db_session)

    request = await service.create_request(
        user_id=1,
        category="тест",
        address="Тестовый адрес",
        description="Тестовая заявка",
        urgency="обычная"
    )

    # Проверяем, что номер сгенерирован правильно
    assert request.request_number is not None
    assert RequestNumberService.validate_request_number_format(request.request_number)

    # Проверяем остальные поля
    assert request.category == "тест"
    assert request.status == "новая"
```

**Запуск тестов**:
```bash
# Запустить все тесты
docker-compose -f docker-compose.dev.yml exec app pytest

# Запустить конкретный тест
docker-compose -f docker-compose.dev.yml exec app pytest tests/test_request_service.py::test_create_request -v

# С покрытием кода
docker-compose -f docker-compose.dev.yml exec app pytest --cov=uk_management_bot --cov-report=html
```

---

## 📚 Полезные команды

### Работа с базой данных

```bash
# Применить миграции
docker-compose -f docker-compose.dev.yml exec app alembic upgrade head

# Создать миграцию
docker-compose -f docker-compose.dev.yml exec app alembic revision --autogenerate -m "Description"

# Откатить миграцию
docker-compose -f docker-compose.dev.yml exec app alembic downgrade -1

# Посмотреть историю миграций
docker-compose -f docker-compose.dev.yml exec app alembic history
```

### Отладка

```python
# Включить детальные логи
import logging
logging.basicConfig(level=logging.DEBUG)

# Посмотреть SQL-запросы
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    print("Executing SQL:")
    print(statement)
    print("Parameters:", parameters)
```

---

## 🎯 Следующие шаги

1. **Изучите документацию**: [API_DOCUMENTATION.md](MemoryBank/API_DOCUMENTATION.md)
2. **Попробуйте Swagger UI**: Откройте `openapi.yaml` в [Swagger Editor](https://editor.swagger.io/)
3. **Запустите тесты**: `docker-compose -f docker-compose.dev.yml exec app pytest`
4. **Создайте свою заявку**: Используйте примеры выше
5. **Экспериментируйте**: Модифицируйте примеры под свои задачи

---

## 💡 Советы

- ✅ Всегда используйте `async/await` для сервисов
- ✅ Проверяйте результаты на `None` перед использованием
- ✅ Используйте `try/finally` для закрытия сессий БД
- ✅ Для production используйте переменные окружения для секретов
- ✅ Включайте логирование для отладки
- ⚠️ Не забывайте про rate limiting при переключении ролей
- ⚠️ Используйте `request_number` (строка), а не `request_id` (int)

---

**Версия**: 2.1.0
**Последнее обновление**: 27.10.2025
**Автор**: UK Management Bot Team
