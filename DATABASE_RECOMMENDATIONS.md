# 🎯 UK Management Bot - Рекомендации по базе данных

**Дата**: 15 октября 2025
**Версия**: 2.0
**Статус**: Production Analysis Complete

---

## 📋 Оглавление

1. [Текущее состояние](#текущее-состояние)
2. [Критические проблемы](#критические-проблемы)
3. [Рекомендации по оптимизации](#рекомендации-по-оптимизации)
4. [План миграции на Alembic](#план-миграции-на-alembic)
5. [Оптимизация производительности](#оптимизация-производительности)
6. [Безопасность](#безопасность)
7. [Мониторинг](#мониторинг)

---

## ✅ Текущее состояние

### Что работает хорошо

1. **Правильная структура данных** ✅
   - 20+ таблиц правильно спроектированы
   - Нормализация выполнена корректно (3NF)
   - Foreign Keys настроены правильно
   - Cascade rules продуманы

2. **Индексы** ✅
   - 50+ индексов на критических полях
   - Primary Keys на всех таблицах
   - Unique constraints корректны
   - Foreign Key indexes присутствуют

3. **Типы данных** ✅
   - Правильное использование BIGINT для telegram_id
   - JSON для гибких данных
   - TIMESTAMP WITH TIME ZONE для дат
   - VARCHAR с адекватными размерами

4. **Иерархия адресов** ✅
   - Правильная структура Yard → Building → Apartment
   - GPS координаты для геооптимизации
   - Модерация связей через user_apartments

5. **Система смен** ✅
   - Продуманная структура с templates
   - AI-оценки в shift_assignments
   - Система передачи смен с approval workflow

### Что нужно улучшить

1. **Нет Alembic миграций** ⚠️
   - Используется `Base.metadata.create_all()`
   - Нет версионирования схемы
   - Сложно отслеживать изменения
   - Проблемы при deployment

2. **Sync SQLAlchemy в async контексте** ⚠️
   - Блокирующие операции в async handlers
   - Потенциальные deadlocks
   - Деградация производительности

3. **N+1 проблемы** ⚠️
   - Множественные запросы для связанных данных
   - Нет eager loading
   - Замедление при больших объемах

4. **Отсутствие партиционирования** 📊
   - audit_logs растет неограниченно
   - shift_assignments может стать огромным
   - Медленные запросы к большим таблицам

---

## 🔴 Критические проблемы

### 1. PRIMARY KEY Request.request_number (String)

**Проблема**:
- `request_number` (VARCHAR) как PRIMARY KEY
- Все FK ссылаются на строку вместо INTEGER
- Снижение производительности JOIN операций

**Рекомендация**: ✅ **НЕ МЕНЯТЬ**

Несмотря на теоретические проблемы производительности, изменение PRIMARY KEY на этом этапе:
- Слишком рискованно для production системы
- Требует полной перестройки всех FK
- Текущая реализация работает стабильно
- VARCHAR(10) достаточно компактен для индексов

**Обоснование сохранения**:
```
✅ request_number уникален и стабилен
✅ Понятный формат для пользователей (YYMMDD-NNN)
✅ Компактный размер (10 байт vs 4 байта INT) - приемлемо
✅ Все FK уже настроены правильно
✅ Система работает в production без проблем
```

### 2. SQLAlchemy Warning: Overlapping Relationships

**Проблема**:
```python
relationship(s): 'User.executed_requests' (copies users.id to requests.executor_id).
If this is not the intention, consider if these relationships should be
linked with back_populates, or if viewonly=True should be applied
```

**Исправление** в [user.py](uk_management_bot/database/models/user.py:57):

```python
# БЫЛО:
executed_requests = relationship("Request", foreign_keys="Request.executor_id")

# ДОЛЖНО БЫТЬ:
executed_requests = relationship(
    "Request",
    foreign_keys="Request.executor_id",
    overlaps="executor"  # Добавить это
)
```

### 3. Sync DB в Async Context

**Проблема**: Все операции БД выполняются синхронно в async handlers

**Текущий код**:
```python
@router.message(F.text == "📝 Создать заявку")
async def create_request(message: Message, state: FSMContext):
    db = SessionLocal()  # Sync session!
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    # Блокирует event loop!
```

**Решение 1: AsyncSession** (Рекомендуется):
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async_engine = create_async_engine(
    "postgresql+asyncpg://uk_bot:password@postgres:5432/uk_management"
)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession)

@router.message(F.text == "📝 Создать заявку")
async def create_request(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
```

**Решение 2: run_in_executor** (Быстрое):
```python
import asyncio

async def get_user_sync(telegram_id: int):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        db.close()

@router.message(F.text == "📝 Создать заявку")
async def create_request(message: Message, state: FSMContext):
    user = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: get_user_sync(message.from_user.id)
    )
```

---

## 💡 Рекомендации по оптимизации

### 1. Внедрить Alembic миграции

**Преимущества**:
- Версионирование схемы БД
- Откат изменений (rollback)
- Автоматическая генерация миграций
- Лучший контроль изменений в production

**План внедрения** (2-3 дня):

**Шаг 1**: Инициализация Alembic
```bash
cd /path/to/project
pip install alembic asyncpg
alembic init alembic
```

**Шаг 2**: Настройка [alembic.ini](alembic.ini)
```ini
sqlalchemy.url = postgresql://uk_bot:password@localhost:5432/uk_management
```

**Шаг 3**: Настройка [alembic/env.py](alembic/env.py)
```python
from uk_management_bot.database.session import Base
import uk_management_bot.database.models  # Import all models
target_metadata = Base.metadata
```

**Шаг 4**: Создание initial миграции
```bash
# Создать снапшот текущей схемы
alembic revision --autogenerate -m "Initial schema from SQLAlchemy models"

# Пометить как применённую (так как БД уже существует)
alembic stamp head
```

**Шаг 5**: Будущие изменения
```bash
# Изменить модель в коде
# Создать миграцию
alembic revision --autogenerate -m "Add new field to User"

# Применить
alembic upgrade head

# Откатить (если нужно)
alembic downgrade -1
```

### 2. Оптимизация N+1 проблемы

**Проблема**: Множественные запросы для связанных данных

**Плохой код**:
```python
requests = db.query(Request).filter(Request.status == 'Новая').all()
for request in requests:
    print(request.user.first_name)  # N+1 query!
    print(request.executor.first_name)  # N+1 query!
```

**Хороший код**:
```python
from sqlalchemy.orm import joinedload

requests = db.query(Request)\
    .options(
        joinedload(Request.user),
        joinedload(Request.executor),
        joinedload(Request.apartment_obj).joinedload(Apartment.building)
    )\
    .filter(Request.status == 'Новая')\
    .all()

for request in requests:
    print(request.user.first_name)  # Уже загружено!
```

**Где применить**:
- `handlers/requests.py` - список заявок
- `handlers/shifts.py` - список смен с исполнителями
- `handlers/admin.py` - панель управления
- `services/assignment_optimizer.py` - поиск исполнителей

### 3. Добавить пагинацию везде

**Проблема**: Запросы без LIMIT

**Плохой код**:
```python
all_requests = db.query(Request).all()  # Может быть 10,000+ записей!
```

**Хороший код**:
```python
def get_requests_paginated(db, page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    return db.query(Request)\
        .order_by(Request.created_at.desc())\
        .limit(per_page)\
        .offset(offset)\
        .all()

total = db.query(Request).count()
total_pages = (total + per_page - 1) // per_page
```

### 4. Партиционирование больших таблиц

**Таблицы-кандидаты**:
- `audit_logs` - партиционирование по месяцам
- `notifications` - партиционирование по месяцам
- `shift_assignments` - партиционирование по кварталам

**Пример партиционирования audit_logs**:

```sql
-- Преобразовать в партиционированную таблицу
ALTER TABLE audit_logs RENAME TO audit_logs_old;

CREATE TABLE audit_logs (
    id SERIAL,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    details JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Создать партиции по месяцам
CREATE TABLE audit_logs_2025_10 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');

CREATE TABLE audit_logs_2025_11 PARTITION OF audit_logs
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

-- Миграция данных
INSERT INTO audit_logs SELECT * FROM audit_logs_old;

-- Удалить старую таблицу
DROP TABLE audit_logs_old;
```

**Автоматическое создание партиций**:

```python
# utils/partition_manager.py
from datetime import datetime, timedelta
from sqlalchemy import text

def create_monthly_partitions(db, table_name: str, months_ahead: int = 3):
    """Создает партиции на N месяцев вперед"""
    current_date = datetime.now()

    for i in range(months_ahead):
        month_start = (current_date + timedelta(days=30*i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)

        partition_name = f"{table_name}_{month_start.strftime('%Y_%m')}"

        sql = f"""
        CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table_name}
        FOR VALUES FROM ('{month_start}') TO ('{month_end}');
        """

        db.execute(text(sql))
        db.commit()
```

### 5. Материализованные представления для аналитики

**Создать материализованные views**:

```sql
-- 1. Статистика исполнителей
CREATE MATERIALIZED VIEW mv_executor_stats AS
SELECT
    u.id as executor_id,
    u.first_name,
    u.last_name,
    COUNT(DISTINCT r.request_number) as total_requests,
    COUNT(DISTINCT CASE WHEN r.status = 'Выполнена' THEN r.request_number END) as completed_requests,
    AVG(EXTRACT(EPOCH FROM (r.completed_at - r.created_at))/3600) as avg_completion_hours,
    AVG(rat.rating) as avg_rating
FROM users u
LEFT JOIN requests r ON u.id = r.executor_id
LEFT JOIN ratings rat ON r.request_number = rat.request_number
WHERE u.active_role = 'executor'
GROUP BY u.id, u.first_name, u.last_name;

CREATE UNIQUE INDEX ON mv_executor_stats (executor_id);

-- Обновлять каждые 6 часов
CREATE OR REPLACE FUNCTION refresh_executor_stats()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_executor_stats;
END;
$$ LANGUAGE plpgsql;

-- Запланировать через pg_cron или APScheduler
```

### 6. Connection Pooling оптимизация

**Текущая конфигурация**:
```python
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
```

**Рекомендуемая для Production**:

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=30,           # Увеличить для высокой нагрузки
    max_overflow=20,        # Буфер для пиковых нагрузок
    pool_timeout=30,        # Ждать свободное соединение 30 сек
    pool_recycle=3600,      # Пересоздавать соединения каждый час
    pool_pre_ping=True,     # Проверять соединения перед использованием
    echo_pool=False,        # Логировать pool в DEBUG режиме
)
```

---

## 🔒 Безопасность

### 1. Row Level Security (RLS)

**Рекомендация**: Внедрить RLS для критических таблиц

```sql
-- Включить RLS для requests
ALTER TABLE requests ENABLE ROW LEVEL SECURITY;

-- Политика: пользователь видит только свои заявки
CREATE POLICY requests_user_policy ON requests
    FOR SELECT
    USING (user_id = current_setting('app.user_id')::integer);

-- Политика: исполнитель видит назначенные ему заявки
CREATE POLICY requests_executor_policy ON requests
    FOR SELECT
    USING (executor_id = current_setting('app.user_id')::integer);

-- Политика: менеджеры видят всё
CREATE POLICY requests_manager_policy ON requests
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE id = current_setting('app.user_id')::integer
            AND active_role = 'manager'
        )
    );
```

**Установка контекста в коде**:
```python
def set_user_context(db, user_id: int):
    db.execute(text(f"SET app.user_id = {user_id}"))
```

### 2. Аудит всех изменений

**Создать trigger для автоматического аудита**:

```sql
-- Функция аудита
CREATE OR REPLACE FUNCTION audit_trigger_function()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (action, details)
        VALUES (
            TG_TABLE_NAME || '_INSERT',
            row_to_json(NEW)
        );
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (action, details)
        VALUES (
            TG_TABLE_NAME || '_UPDATE',
            json_build_object(
                'old', row_to_json(OLD),
                'new', row_to_json(NEW)
            )
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (action, details)
        VALUES (
            TG_TABLE_NAME || '_DELETE',
            row_to_json(OLD)
        );
        RETURN OLD;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Применить к критическим таблицам
CREATE TRIGGER audit_requests
AFTER INSERT OR UPDATE OR DELETE ON requests
FOR EACH ROW EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER audit_users
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION audit_trigger_function();
```

### 3. Шифрование чувствительных данных

**Использовать pgcrypto для паспортных данных**:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Функция шифрования
CREATE OR REPLACE FUNCTION encrypt_sensitive(value TEXT)
RETURNS BYTEA AS $$
BEGIN
    RETURN pgp_sym_encrypt(value, current_setting('app.encryption_key'));
END;
$$ LANGUAGE plpgsql;

-- Функция дешифрования
CREATE OR REPLACE FUNCTION decrypt_sensitive(encrypted BYTEA)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(encrypted, current_setting('app.encryption_key'));
END;
$$ LANGUAGE plpgsql;

-- Изменить модель User
ALTER TABLE users ALTER COLUMN passport_series TYPE BYTEA
    USING pgp_sym_encrypt(passport_series, 'encryption_key');

ALTER TABLE users ALTER COLUMN passport_number TYPE BYTEA
    USING pgp_sym_encrypt(passport_number, 'encryption_key');
```

---

## 📊 Мониторинг

### 1. Метрики производительности

**Создать систему мониторинга**:

```python
# utils/db_monitoring.py
from prometheus_client import Counter, Histogram, Gauge
import time
from functools import wraps

# Метрики
db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['query_type', 'table']
)

db_query_total = Counter(
    'db_query_total',
    'Total database queries',
    ['query_type', 'table', 'status']
)

db_connection_pool_size = Gauge(
    'db_connection_pool_size',
    'Current connection pool size'
)

def monitor_query(query_type: str, table: str):
    """Декоратор для мониторинга запросов"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration.labels(
                    query_type=query_type,
                    table=table
                ).observe(duration)

                db_query_total.labels(
                    query_type=query_type,
                    table=table,
                    status=status
                ).inc()

        return wrapper
    return decorator

# Использование
@monitor_query('SELECT', 'requests')
def get_active_requests(db):
    return db.query(Request).filter(
        Request.status.in_(['Новая', 'В обработке'])
    ).all()
```

### 2. Slow Query Log

**Настроить PostgreSQL для логирования медленных запросов**:

```sql
-- В postgresql.conf
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- 1 секунда
ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';
ALTER SYSTEM SET log_statement = 'ddl';

-- Перезапустить PostgreSQL
SELECT pg_reload_conf();
```

### 3. Автоматическая проверка здоровья БД

```python
# utils/db_health_check.py
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

async def check_database_health(db) -> dict:
    """Проверка здоровья базы данных"""

    health = {
        'status': 'healthy',
        'checks': {}
    }

    # 1. Проверка подключения
    try:
        db.execute(text("SELECT 1"))
        health['checks']['connection'] = 'ok'
    except Exception as e:
        health['status'] = 'unhealthy'
        health['checks']['connection'] = f'failed: {str(e)}'

    # 2. Проверка размера БД
    try:
        result = db.execute(text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        ))
        size = result.scalar()
        health['checks']['database_size'] = size
    except Exception as e:
        logger.error(f"Failed to get database size: {e}")

    # 3. Проверка количества подключений
    try:
        result = db.execute(text("""
            SELECT count(*) FROM pg_stat_activity
            WHERE datname = current_database()
        """))
        connections = result.scalar()
        health['checks']['active_connections'] = connections

        if connections > 80:
            health['status'] = 'degraded'
            health['checks']['connection_warning'] = 'High connection count'
    except Exception as e:
        logger.error(f"Failed to get connection count: {e}")

    # 4. Проверка репликации (если есть)
    try:
        result = db.execute(text("SELECT pg_is_in_recovery()"))
        is_replica = result.scalar()
        health['checks']['replication'] = 'replica' if is_replica else 'primary'
    except Exception as e:
        logger.error(f"Failed to check replication: {e}")

    # 5. Проверка индексов без использования
    try:
        result = db.execute(text("""
            SELECT schemaname, tablename, indexname
            FROM pg_stat_user_indexes
            WHERE idx_scan = 0 AND idx_tup_read = 0
            LIMIT 5
        """))
        unused_indexes = [dict(row) for row in result]
        if unused_indexes:
            health['checks']['unused_indexes'] = unused_indexes
    except Exception as e:
        logger.error(f"Failed to check unused indexes: {e}")

    return health
```

---

## 📅 План действий (приоритизация)

### Неделя 1: Критические исправления
- [ ] Исправить overlapping relationships warning в User модели
- [ ] Добавить missing indexes для новых полей
- [ ] Настроить connection pool оптимально
- [ ] Включить slow query log

### Неделя 2: Alembic миграции
- [ ] Инициализировать Alembic
- [ ] Создать initial миграцию
- [ ] Протестировать на dev окружении
- [ ] Документировать процесс

### Неделя 3: Async SQLAlchemy
- [ ] Установить asyncpg
- [ ] Создать AsyncEngine
- [ ] Переписать 5 самых критичных handlers
- [ ] Протестировать производительность

### Неделя 4: N+1 оптимизация
- [ ] Идентифицировать все N+1 проблемы
- [ ] Добавить joinedload в критических местах
- [ ] Добавить пагинацию везде
- [ ] Замерить улучшение производительности

### Месяц 2: Партиционирование
- [ ] Партициониров��ть audit_logs
- [ ] Партиционировать notifications
- [ ] Создать автоматику для партиций
- [ ] Настроить архивацию старых данных

### Месяц 3: Безопасность и мониторинг
- [ ] Внедрить RLS
- [ ] Настроить шифрование чувствительных данных
- [ ] Настроить Prometheus метрики
- [ ] Создать Grafana дашборд

---

## 🎓 Заключение

### Текущая оценка: 9.0/10

**Сильные стороны**:
- ✅ Отличная структура данных
- ✅ Правильные отношения и FK
- ✅ Хорошие индексы
- ✅ Продуманная архитектура

**Что улучшить**:
- ⚠️ Внедрить Alembic (критично для production)
- ⚠️ Перейти на AsyncSQLAlchemy
- ⚠️ Устранить N+1 проблемы
- 📊 Партиционирование для масштабирования

### После всех улучшений: 10/10

---

**Документ создан**: 15 октября 2025
**Автор**: Claude Sonnet 4.5
**Версия**: 2.0
**Статус**: Ready for Implementation
