# 🗄️ PostgreSQL Initialization Scripts

Этот каталог содержит скрипты для автоматической инициализации PostgreSQL базы данных для UK Management Bot с **точно такой же структурой как в SQLite**.

## 📁 Файлы

### 🐘 Основные скрипты инициализации

#### `init_postgres.sql`
- **Назначение**: Основной SQL скрипт инициализации
- **Выполняется**: Автоматически при первом запуске PostgreSQL контейнера
- **Функции**:
  - Создание базы данных `uk_management`
  - Создание пользователя `uk_bot`
  - Настройка прав доступа
  - Включение расширений (uuid-ossp, pg_trgm, pg_stat_statements)
  - **Создание всех таблиц с точно такой же структурой как в SQLite**
  - Применение миграций (эквивалент SQLite миграций)
  - Создание триггеров и ограничений

#### `init_postgres.sh`
- **Назначение**: Bash скрипт дополнительной настройки
- **Выполняется**: После SQL скрипта
- **Функции**:
  - Проверка готовности PostgreSQL
  - Дополнительная настройка прав
  - Создание таблиц мониторинга
  - Тестирование подключений
  - Создание тестовых данных (опционально)

#### `check_postgres_init.sh`
- **Назначение**: Скрипт проверки инициализации
- **Выполняется**: Вручную для проверки
- **Функции**:
  - Проверка всех компонентов базы данных
  - **Проверка структуры таблиц (совместимость с SQLite)**
  - Проверка индексов, триггеров и ограничений
  - Тестирование операций
  - Проверка производительности
  - Вывод сводки

### 🔧 Существующие скрипты

#### `init_db.py`
- **Назначение**: Python скрипт инициализации SQLAlchemy моделей
- **Выполняется**: После создания базы данных
- **Функции**:
  - Создание таблиц через SQLAlchemy
  - Применение миграций
  - Инициализация данных

#### `grant_roles.py`
- **Назначение**: Скрипт управления ролями пользователей
- **Выполняется**: Для настройки ролей
- **Функции**:
  - Создание ролей пользователей
  - Назначение прав
  - Управление доступом

## 🚀 Использование

### Автоматическая инициализация

Скрипты автоматически выполняются при запуске Docker контейнера:

```bash
# Запуск с автоматической инициализацией
docker-compose up -d
```

### Ручная проверка

```bash
# Проверка инициализации
docker-compose exec postgres bash /docker-entrypoint-initdb.d/check_postgres_init.sh

# Или локально
./scripts/check_postgres_init.sh
```

### Создание тестовых данных

```bash
# Установка переменной окружения для создания тестовых данных
export CREATE_TEST_DATA=true
docker-compose up -d
```

## 📊 Что создается (SQLite-совместимая структура)

### База данных
- **Имя**: `uk_management`
- **Кодировка**: UTF8
- **Владелец**: `postgres`

### Пользователь
- **Имя**: `uk_bot`
- **Пароль**: `uk_bot_password`
- **Права**: Все права на базу данных

### Расширения
- `uuid-ossp` - для генерации UUID
- `pg_trgm` - для полнотекстового поиска
- `pg_stat_statements` - для мониторинга производительности

### Схемы
- `public` - основная схема
- `audit` - для аудита

### Таблицы (точно как в SQLite)

#### `users` - Пользователи
- `id` (SERIAL PRIMARY KEY)
- `telegram_id` (INTEGER UNIQUE NOT NULL)
- `username` (VARCHAR(255))
- `first_name` (VARCHAR(255))
- `last_name` (VARCHAR(255))
- `role` (VARCHAR(50) DEFAULT 'applicant') - историческое поле
- `roles` (TEXT) - новый формат ролей в JSON
- `active_role` (VARCHAR(50)) - активная роль
- `status` (VARCHAR(50) DEFAULT 'pending')
- `language` (VARCHAR(10) DEFAULT 'ru')
- `phone` (VARCHAR(20))
- `address` (TEXT) - существующее поле
- `home_address` (TEXT) - новое поле
- `apartment_address` (TEXT) - новое поле
- `yard_address` (TEXT) - новое поле
- `address_type` (VARCHAR(20)) - тип адреса
- `specialization` (VARCHAR(50))
- `created_at` (TIMESTAMP WITH TIME ZONE)
- `updated_at` (TIMESTAMP WITH TIME ZONE)

#### `requests` - Заявки
- `id` (SERIAL PRIMARY KEY)
- `user_id` (INTEGER REFERENCES users(id))
- `category` (VARCHAR(100))
- `status` (VARCHAR(50) DEFAULT 'Новая')
- `address` (TEXT)
- `description` (TEXT)
- `apartment` (VARCHAR(20))
- `urgency` (VARCHAR(20) DEFAULT 'Обычная')
- `media_files` (JSONB DEFAULT '[]')
- `executor_id` (INTEGER REFERENCES users(id))
- `notes` (TEXT)
- `completion_report` (TEXT)
- `completion_media` (JSONB DEFAULT '[]')
- `created_at` (TIMESTAMP WITH TIME ZONE)
- `updated_at` (TIMESTAMP WITH TIME ZONE)
- `completed_at` (TIMESTAMP WITH TIME ZONE)

#### `shifts` - Смены
- `id` (SERIAL PRIMARY KEY)
- `user_id` (INTEGER REFERENCES users(id))
- `start_time` (TIMESTAMP WITH TIME ZONE)
- `end_time` (TIMESTAMP WITH TIME ZONE)
- `status` (VARCHAR(50) DEFAULT 'active')
- `notes` (TEXT)
- `created_at` (TIMESTAMP WITH TIME ZONE)
- `updated_at` (TIMESTAMP WITH TIME ZONE)

#### `ratings` - Оценки
- `id` (SERIAL PRIMARY KEY)
- `request_id` (INTEGER REFERENCES requests(id))
- `user_id` (INTEGER REFERENCES users(id))
- `rating` (INTEGER) - от 1 до 5
- `review` (TEXT)
- `created_at` (TIMESTAMP WITH TIME ZONE)

#### `audit_logs` - Аудит
- `id` (SERIAL PRIMARY KEY)
- `user_id` (INTEGER REFERENCES users(id))
- `action` (VARCHAR(100))
- `details` (JSONB)
- `ip_address` (VARCHAR(45))
- `created_at` (TIMESTAMP WITH TIME ZONE)

### Таблицы мониторинга
- `connection_log` - логи подключений
- `performance_stats` - статистика производительности

## 🔐 Безопасность

### Права доступа
- Пользователь `uk_bot` имеет только необходимые права
- Нет прав суперпользователя
- Ограниченный доступ к системным функциям

### SSL (для production)
```sql
-- Включить в production
ALTER SYSTEM SET ssl = on;
ALTER SYSTEM SET ssl_cert_file = '/path/to/cert.pem';
ALTER SYSTEM SET ssl_key_file = '/path/to/key.pem';
```

## ⚡ Оптимизация производительности

### Рекомендуемые настройки
```sql
-- Для небольших-средних нагрузок
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
```

### Мониторинг
```sql
-- Проверка производительности
SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;

-- Проверка подключений
SELECT * FROM pg_stat_activity WHERE datname = 'uk_management';
```

## 🔄 Миграции (SQLite-совместимые)

### Примененные миграции
1. **add_user_addresses** - добавление полей адресов
2. **add_user_roles_active_role** - добавление полей ролей

### Бекфилл данных
- Автоматическое заполнение `roles` и `active_role` на основе старого поля `role`
- Установка `address_type = 'home'` для существующих адресов

## 🔒 Ограничения и проверки

### Ограничения данных
- `check_rating_range` - рейтинг от 1 до 5
- `check_request_status` - валидные статусы заявок
- `check_shift_status` - валидные статусы смен
- `check_user_status` - валидные статусы пользователей
- `check_user_language` - валидные языки

### Триггеры
- `update_users_updated_at` - автоматическое обновление `updated_at`
- `update_requests_updated_at` - автоматическое обновление `updated_at`
- `update_shifts_updated_at` - автоматическое обновление `updated_at`

## 🚨 Устранение неполадок

### Проблемы с инициализацией

1. **Проверьте логи PostgreSQL**:
   ```bash
   docker-compose logs postgres
   ```

2. **Проверьте права на файлы**:
   ```bash
   chmod +x scripts/*.sh
   ```

3. **Пересоздайте контейнер**:
   ```bash
   docker-compose down -v
   docker-compose up -d
   ```

### Проблемы с подключением

1. **Проверьте переменные окружения**:
   ```bash
   docker-compose exec app env | grep DATABASE
   ```

2. **Тестируйте подключение**:
   ```bash
   docker-compose exec postgres psql -U uk_bot -d uk_management
   ```

### Проверка совместимости с SQLite

```bash
# Запустите полную проверку структуры
./scripts/check_postgres_init.sh

# Проверьте конкретную таблицу
docker-compose exec postgres psql -U uk_bot -d uk_management -c "\d users"
```

## 📝 Логирование

### Логи инициализации
- Логи PostgreSQL: `docker-compose logs postgres`
- Логи приложения: `docker-compose logs app`

### Мониторинг
```sql
-- Просмотр логов подключений
SELECT * FROM connection_log ORDER BY connection_time DESC LIMIT 10;

-- Просмотр статистики
SELECT * FROM performance_stats ORDER BY timestamp DESC LIMIT 10;

-- Проверка структуры таблиц
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' 
ORDER BY table_name, ordinal_position;
```

## 🔄 Обновление

### Добавление новых таблиц
1. Добавьте SQL в `init_postgres.sql`
2. Обновите `check_postgres_init.sh`
3. Пересоздайте контейнер

### Изменение настроек
1. Отредактируйте скрипты
2. Пересоздайте контейнер с `docker-compose down -v`

### Миграция данных из SQLite
```bash
# Экспорт из SQLite
sqlite3 uk_management.db ".dump" > sqlite_dump.sql

# Импорт в PostgreSQL (требует адаптации)
psql -U uk_bot -d uk_management < adapted_sqlite_dump.sql
```

## ✅ Совместимость

### SQLite vs PostgreSQL
| Аспект | SQLite | PostgreSQL |
|--------|--------|------------|
| **Структура таблиц** | ✅ Идентичная | ✅ Идентичная |
| **Типы данных** | ✅ Совместимые | ✅ Совместимые |
| **Индексы** | ✅ Создаются | ✅ Создаются |
| **Ограничения** | ✅ Применяются | ✅ Применяются |
| **Миграции** | ✅ Применены | ✅ Применены |
| **Триггеры** | ❌ Нет | ✅ Автоматические |

---

**PostgreSQL инициализация готова для UK Management Bot с полной совместимостью с SQLite! 🚀**
