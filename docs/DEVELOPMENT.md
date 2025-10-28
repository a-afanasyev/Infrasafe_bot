# 🚀 UK Management Bot - Development Guide

## 📋 Быстрый старт для разработки

### 1️⃣ Запуск в режиме разработки

```bash
# Остановить production контейнеры
docker-compose down

# Запустить development окружение
docker-compose -f docker-compose.dev.yml up -d

# Посмотреть логи
docker-compose -f docker-compose.dev.yml logs -f app
```

### 2️⃣ Hot-Reload (изменения без пересборки)

После запуска development окружения:

1. **Вносите изменения в код** в папке `uk_management_bot/`
2. **Перезапускайте только приложение**:
   ```bash
   docker-compose -f docker-compose.dev.yml restart app
   ```
3. **Или перезапускайте автоматически** при изменениях:
   ```bash
   # В отдельном терминале
   docker-compose -f docker-compose.dev.yml logs -f app
   ```

## 🔧 Структура Development окружения

### Dockerfile.dev
- **Основа**: Python 3.11-slim
- **Зависимости**: Устанавливаются при сборке
- **Код**: Монтируется как volume
- **Переменные**: DEBUG=true, LOG_LEVEL=DEBUG

### docker-compose.dev.yml
- **Монтирование кода**: `./uk_management_bot:/app/uk_management_bot`
- **Монтирование .env**: `./.env:/app/.env`
- **Монтирование скриптов**: `./scripts:/app/scripts`
- **База данных**: PostgreSQL с инициализацией
- **Redis**: Для rate limiting

## 📊 Миграция данных

### Перенос из SQLite в PostgreSQL

```bash
# Запустить development окружение
docker-compose -f docker-compose.dev.yml up -d

# Выполнить миграцию
python scripts/migrate_sqlite_to_postgres.py
```

### Проверка данных

```bash
# Подключиться к PostgreSQL
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management

# Проверить данные
\dt
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM requests;
```

## 🛠️ Команды для разработки

### Управление контейнерами

```bash
# Запуск
docker-compose -f docker-compose.dev.yml up -d

# Остановка
docker-compose -f docker-compose.dev.yml down

# Перезапуск только приложения
docker-compose -f docker-compose.dev.yml restart app

# Перезапуск с пересборкой
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml build --no-cache
docker-compose -f docker-compose.dev.yml up -d
```

### Логи и отладка

```bash
# Логи приложения
docker-compose -f docker-compose.dev.yml logs -f app

# Логи PostgreSQL
docker-compose -f docker-compose.dev.yml logs -f postgres

# Логи Redis
docker-compose -f docker-compose.dev.yml logs -f redis

# Все логи
docker-compose -f docker-compose.dev.yml logs -f
```

### База данных

```bash
# Подключение к PostgreSQL
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management

# Сброс базы данных
docker-compose -f docker-compose.dev.yml down -v
docker-compose -f docker-compose.dev.yml up -d

# Резервная копия
docker-compose -f docker-compose.dev.yml exec postgres pg_dump -U uk_bot uk_management > backup.sql

# Восстановление
docker-compose -f docker-compose.dev.yml exec -T postgres psql -U uk_bot -d uk_management < backup.sql
```

## 🔍 Отладка

### Проверка статуса

```bash
# Статус контейнеров
docker-compose -f docker-compose.dev.yml ps

# Проверка health check
docker-compose -f docker-compose.dev.yml exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"
```

### Переменные окружения

```bash
# Проверить переменные в контейнере
docker-compose -f docker-compose.dev.yml exec app env | grep -E "(BOT_TOKEN|DATABASE_URL|DEBUG)"
```

### Файлы в контейнере

```bash
# Проверить структуру файлов
docker-compose -f docker-compose.dev.yml exec app ls -la /app

# Проверить код
docker-compose -f docker-compose.dev.yml exec app ls -la /app/uk_management_bot/
```

## 🚨 Устранение неполадок

### Проблемы с подключением к базе данных

```bash
# Проверить PostgreSQL
docker-compose -f docker-compose.dev.yml exec postgres pg_isready -U uk_bot -d uk_management

# Проверить таблицы
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management -c "\dt"
```

### Проблемы с Redis

```bash
# Проверить Redis
docker-compose -f docker-compose.dev.yml exec redis redis-cli ping

# Проверить ключи
docker-compose -f docker-compose.dev.yml exec redis redis-cli keys "*"
```

### Проблемы с кодом

```bash
# Проверить синтаксис Python
docker-compose -f docker-compose.dev.yml exec app python -m py_compile uk_management_bot/main.py

# Запустить с отладкой
docker-compose -f docker-compose.dev.yml exec app python -u uk_management_bot/main.py
```

## 📝 Workflow разработки

### 1. Начало работы
```bash
# Запустить development окружение
docker-compose -f docker-compose.dev.yml up -d

# Проверить статус
docker-compose -f docker-compose.dev.yml ps
```

### 2. Разработка
```bash
# Вносить изменения в код
# Перезапускать приложение при необходимости
docker-compose -f docker-compose.dev.yml restart app

# Следить за логами
docker-compose -f docker-compose.dev.yml logs -f app
```

### 3. Тестирование
```bash
# Проверить работу бота в Telegram
# Проверить базу данных
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management
```

### 4. Завершение работы
```bash
# Остановить development окружение
docker-compose -f docker-compose.dev.yml down

# При необходимости сохранить данные
docker-compose -f docker-compose.dev.yml exec postgres pg_dump -U uk_bot uk_management > dev_backup.sql
```

## 🔄 Переключение между режимами

### Development → Production
```bash
# Остановить development
docker-compose -f docker-compose.dev.yml down

# Запустить production
docker-compose up -d
```

### Production → Development
```bash
# Остановить production
docker-compose down

# Запустить development
docker-compose -f docker-compose.dev.yml up -d
```

## 📚 Полезные команды

### Очистка
```bash
# Удалить все контейнеры и volumes
docker-compose -f docker-compose.dev.yml down -v
docker system prune -f
```

### Мониторинг
```bash
# Использование ресурсов
docker stats

# Размер образов
docker images

# Размер volumes
docker volume ls
```

---

**🎯 Теперь вы можете разрабатывать с hot-reload! Изменения в коде применяются без пересборки контейнера.**
