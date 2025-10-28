# Единое Развертывание: Bot + Media Service

Руководство по запуску UK Management Bot и Media Service в едином Docker окружении.

---

## 📋 Требования

- Docker 20.10+
- Docker Compose 2.0+
- Минимум 2 GB свободной оперативной памяти
- Порты: 5432, 6379, 8009, 8010 должны быть свободны

---

## 🚀 Быстрый Старт

### 1. Подготовка окружения

```bash
# Убедитесь что .env файл настроен
cp .env.example .env
nano .env  # Установите BOT_TOKEN и другие параметры
```

### 2. Запуск всех сервисов

```bash
# Одной командой запустить всё
./start-unified.sh
```

Скрипт автоматически:
- ✅ Проверит наличие .env и BOT_TOKEN
- ✅ Создаст необходимые директории
- ✅ Остановит старые контейнеры
- ✅ Запустит все сервисы
- ✅ Покажет статус

### 3. Проверка работы

После запуска доступны:

| Сервис | URL | Описание |
|--------|-----|----------|
| **Media Service API** | http://localhost:8009 | REST API для загрузки медиа |
| **Media Frontend** | http://localhost:8010 | Веб-интерфейс для тестирования |
| **PostgreSQL** | localhost:5432 | База данных |
| **Redis** | localhost:6379 | Кеш и очереди |
| **Telegram Bot** | - | Работает через Telegram API |

---

## 🛠️ Управление

### Просмотр логов

```bash
# Все сервисы
./logs-unified.sh

# Конкретный сервис
./logs-unified.sh bot                # Логи бота
./logs-unified.sh media-service      # Логи медиа API
./logs-unified.sh media-frontend     # Логи фронтенда
./logs-unified.sh postgres           # Логи БД
./logs-unified.sh redis              # Логи Redis
```

### Перезапуск сервисов

```bash
# Все сервисы
./restart-unified.sh

# Конкретный сервис
./restart-unified.sh bot
./restart-unified.sh media-service
```

### Остановка

```bash
# Остановить все сервисы
./stop-unified.sh

# Остановить и удалить volumes (ОСТОРОЖНО!)
docker-compose -f docker-compose.unified.yml down -v
```

---

## 📦 Архитектура

```
┌─────────────────────────────────────────────────────┐
│              UK Management System                    │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐      ┌──────────────────┐         │
│  │ Telegram Bot│◄────►│  Media Service   │         │
│  │   (bot)     │      │  API (FastAPI)   │         │
│  │  Port: -    │      │  Port: 8009      │         │
│  └──────┬──────┘      └────────┬─────────┘         │
│         │                      │                     │
│         │                      │                     │
│         ▼                      ▼                     │
│  ┌──────────────────────────────────┐               │
│  │       PostgreSQL Database        │               │
│  │          Port: 5432              │               │
│  └──────────────────────────────────┘               │
│                                                       │
│  ┌──────────────────────────────────┐               │
│  │          Redis Cache             │               │
│  │          Port: 6379              │               │
│  │  DB 0: Bot  |  DB 1: Media       │               │
│  └──────────────────────────────────┘               │
│                                                       │
│  ┌──────────────────────────────────┐               │
│  │      Media Frontend (Nginx)      │               │
│  │          Port: 8010              │               │
│  └──────────────────────────────────┘               │
│                                                       │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 Конфигурация

### Структура файлов

```
UK/
├── docker-compose.unified.yml    # Главный файл Docker Compose
├── start-unified.sh              # Скрипт запуска
├── stop-unified.sh               # Скрипт остановки
├── logs-unified.sh               # Скрипт просмотра логов
├── restart-unified.sh            # Скрипт перезапуска
├── .env                          # Переменные окружения
├── uk_management_bot/            # Код бота
├── media_service/                # Код медиа-сервиса
│   ├── app/                      # FastAPI приложение
│   ├── frontend/                 # Тестовый веб-интерфейс
│   ├── Dockerfile                # Dockerfile для API
│   └── channels.json             # Конфигурация каналов
└── scripts/                      # Вспомогательные скрипты
```

### Переменные окружения

Основные переменные в `.env`:

```bash
# Telegram Bot
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321

# Database
DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management

# Redis
REDIS_URL=redis://redis:6379/0

# Media Service
MEDIA_SERVICE_URL=http://media-service:8000
MAX_FILE_SIZE=52428800  # 50 MB
ALLOWED_EXTENSIONS=jpg,jpeg,png,gif,mp4,mov,avi,pdf,doc,docx,xls,xlsx

# Development
LOG_LEVEL=DEBUG
DEBUG=true
```

---

## 🧪 Тестирование

### Проверка здоровья сервисов

```bash
# PostgreSQL
docker-compose -f docker-compose.unified.yml exec postgres pg_isready -U uk_bot

# Redis
docker-compose -f docker-compose.unified.yml exec redis redis-cli ping

# Media Service API
curl http://localhost:8009/api/v1/health

# Frontend
curl http://localhost:8010/
```

### Запуск тестов

```bash
# Тесты бота (в контейнере)
docker-compose -f docker-compose.unified.yml exec bot pytest

# Тесты медиа-сервиса
docker-compose -f docker-compose.unified.yml exec media-service pytest
```

### Тестовая загрузка файла

```bash
# Через curl
curl -X POST "http://localhost:8009/api/v1/media/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/file.jpg" \
  -F "channel_id=test_channel"

# Или откройте веб-интерфейс
open http://localhost:8010
```

---

## 🔍 Отладка

### Проблемы с запуском

**Проблема**: Порт уже занят
```bash
# Найти процесс на порту
lsof -i :8009
lsof -i :5432

# Остановить другие Docker контейнеры
docker ps
docker stop <container_id>
```

**Проблема**: Недостаточно памяти
```bash
# Очистить неиспользуемые образы и контейнеры
docker system prune -a

# Увеличить память для Docker (Docker Desktop)
# Settings -> Resources -> Memory -> 4GB+
```

### Проверка логов ошибок

```bash
# Последние 100 строк логов с ошибками
./logs-unified.sh bot | grep -i error | tail -100
./logs-unified.sh media-service | grep -i error | tail -100

# Логи конкретного контейнера
docker logs uk-bot --tail 100 -f
docker logs uk-media-service --tail 100 -f
```

### Подключение к базе данных

```bash
# PostgreSQL CLI
docker-compose -f docker-compose.unified.yml exec postgres \
  psql -U uk_bot -d uk_management

# Redis CLI
docker-compose -f docker-compose.unified.yml exec redis redis-cli

# Просмотр данных Redis
docker-compose -f docker-compose.unified.yml exec redis redis-cli
> SELECT 0  # База бота
> KEYS *
> SELECT 1  # База медиа-сервиса
> KEYS *
```

---

## 📊 Мониторинг

### Проверка статуса контейнеров

```bash
# Статус всех сервисов
docker-compose -f docker-compose.unified.yml ps

# Использование ресурсов
docker stats

# Healthcheck статус
docker inspect --format='{{.State.Health.Status}}' uk-bot
docker inspect --format='{{.State.Health.Status}}' uk-media-service
```

### Метрики производительности

```bash
# Статистика PostgreSQL
docker-compose -f docker-compose.unified.yml exec postgres \
  psql -U uk_bot -d uk_management -c "SELECT * FROM pg_stat_activity;"

# Статистика Redis
docker-compose -f docker-compose.unified.yml exec redis redis-cli INFO stats
```

---

## 🔄 Обновление

### Обновление кода (hot-reload)

Благодаря volume mapping, изменения кода применяются автоматически:

```bash
# Редактируем код
nano uk_management_bot/handlers/admin.py

# Сохраняем - бот автоматически перезагрузится
# (если используется hot-reload)

# Для применения изменений требований
docker-compose -f docker-compose.unified.yml restart bot
```

### Полная пересборка

```bash
# Пересобрать все образы
docker-compose -f docker-compose.unified.yml build

# Пересобрать конкретный сервис
docker-compose -f docker-compose.unified.yml build bot
docker-compose -f docker-compose.unified.yml build media-service

# Перезапустить с пересборкой
docker-compose -f docker-compose.unified.yml up -d --build
```

---

## 🚨 Резервное копирование

### База данных

```bash
# Создать backup
docker-compose -f docker-compose.unified.yml exec postgres \
  pg_dump -U uk_bot uk_management > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановить из backup
docker-compose -f docker-compose.unified.yml exec -T postgres \
  psql -U uk_bot uk_management < backup_20241015_120000.sql
```

### Медиа файлы

```bash
# Backup загруженных файлов
docker run --rm -v uk_media_uploads:/data -v $(pwd):/backup \
  alpine tar czf /backup/media_backup_$(date +%Y%m%d).tar.gz /data

# Восстановление
docker run --rm -v uk_media_uploads:/data -v $(pwd):/backup \
  alpine tar xzf /backup/media_backup_20241015.tar.gz -C /
```

---

## 📚 Дополнительные команды

### Docker Compose команды

```bash
# Показать все контейнеры
docker-compose -f docker-compose.unified.yml ps -a

# Показать использование volumes
docker-compose -f docker-compose.unified.yml config --volumes

# Показать переменные окружения
docker-compose -f docker-compose.unified.yml config

# Выполнить команду в контейнере
docker-compose -f docker-compose.unified.yml exec bot bash
docker-compose -f docker-compose.unified.yml exec media-service sh

# Пересоздать один сервис
docker-compose -f docker-compose.unified.yml up -d --force-recreate bot
```

### Очистка

```bash
# Удалить остановленные контейнеры
docker-compose -f docker-compose.unified.yml rm

# Удалить неиспользуемые образы
docker image prune -a

# Полная очистка (ОСТОРОЖНО!)
docker-compose -f docker-compose.unified.yml down -v
docker system prune -a --volumes
```

---

## 🎯 Миграция с отдельных compose файлов

Если вы использовали раздельные файлы:

```bash
# Остановить старые сервисы
docker-compose -f docker-compose.dev.yml down
docker-compose -f media_service/docker-compose.yml down

# Запустить единое окружение
./start-unified.sh

# Данные в PostgreSQL и Redis сохраняются автоматически
# если используются named volumes
```

---

## 💡 Советы по производительности

1. **Увеличьте лимиты памяти** для Docker Desktop (минимум 4GB)
2. **Используйте SSD** для volumes PostgreSQL
3. **Настройте Redis** максимальную память (в compose файле: 512mb)
4. **Оптимизируйте образы** - используйте multi-stage builds
5. **Мониторьте логи** - используйте log rotation

---

## 📞 Поддержка

Проблемы? Проверьте:
1. Логи: `./logs-unified.sh`
2. Статус: `docker-compose -f docker-compose.unified.yml ps`
3. Healthchecks: `docker inspect <container>`
4. GitHub Issues: [создать issue](https://github.com/your-repo/issues)

---

**Последнее обновление**: 15 октября 2025
**Версия**: 1.0.0
**Статус**: ✅ Production Ready
