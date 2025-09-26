# UK Media Service

Микросервис для управления медиа-файлами через Telegram каналы для UK Management Bot.

## Описание

Media Service предоставляет централизованное хранение и управление медиа-файлами (фото, видео, документы) с использованием приватных Telegram каналов как бесплатного хранилища. Микросервис интегрируется с основным UK Management Bot через REST API.

## Основные возможности

- ✅ Загрузка медиа-файлов в приватные Telegram каналы
- ✅ Универсальный поиск с множественными фильтрами
- ✅ Система тегов для организации контента
- ✅ Статистика и аналитика использования
- ✅ Временные линии для заявок
- ✅ Поиск похожих файлов по тегам
- ✅ Архивация и управление жизненным циклом
- ✅ REST API с OpenAPI документацией
- ✅ Интеграционный клиент для Telegram бота

## Архитектура

```
media_service/
├── app/                    # Основное приложение
│   ├── api/v1/            # REST API endpoints
│   ├── core/              # Конфигурация и настройки
│   ├── db/                # База данных и миграции
│   ├── models/            # SQLAlchemy модели
│   ├── schemas/           # Pydantic схемы
│   ├── services/          # Бизнес-логика
│   └── main.py            # FastAPI приложение
├── client/                # Клиент для интеграции
├── tests/                 # Тесты
├── docker-compose.yml     # Production deployment
├── docker-compose.dev.yml # Development environment
└── Dockerfile             # Container definition
```

## Технологический стек

- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - ORM
- **PostgreSQL** - База данных
- **Redis** - Кэширование
- **Aiogram 3.x** - Telegram Bot API
- **Pydantic** - Валидация данных
- **Docker** - Контейнеризация

## Быстрый старт

### 1. Подготовка

```bash
# Клонирование репозитория
git clone <repository_url>
cd media_service

# Копирование конфигурации
cp .env.example .env
```

### 2. Настройка переменных окружения

Отредактируйте `.env` файл:

```bash
# Обязательные параметры
TELEGRAM_BOT_TOKEN=your_bot_token_here
CHANNEL_REQUESTS=@your_private_channel_requests
CHANNEL_REPORTS=@your_private_channel_reports
CHANNEL_ARCHIVE=@your_private_channel_archive
CHANNEL_BACKUP=@your_private_channel_backup
```

### 3. Запуск для разработки

```bash
# Запуск всех сервисов
docker-compose -f docker-compose.dev.yml up -d

# Просмотр логов
docker-compose -f docker-compose.dev.yml logs -f media-api

# Проверка здоровья
curl http://localhost:8001/api/v1/health
```

### 4. Доступ к сервисам

- **API**: http://localhost:8001
- **Документация**: http://localhost:8001/docs
- **PostgreSQL**: localhost:5434
- **Redis**: localhost:6380
- **PgAdmin**: http://localhost:8082 (admin@uk-media.local / admin123)
- **Redis Commander**: http://localhost:8083

## API Endpoints

### Основные операции

```bash
# Загрузка медиа для заявки
POST /api/v1/media/upload

# Загрузка медиа для отчета
POST /api/v1/media/upload-report

# Поиск медиа-файлов
GET /api/v1/media/search?query=damage&tags=urgent

# Получение медиа заявки
GET /api/v1/media/request/{request_number}

# Получение временной линии
GET /api/v1/media/request/{request_number}/timeline

# Статистика
GET /api/v1/media/statistics

# Популярные теги
GET /api/v1/media/tags/popular
```

### Управление файлами

```bash
# Получение информации о файле
GET /api/v1/media/{media_id}

# Получение URL файла
GET /api/v1/media/{media_id}/url

# Обновление тегов
PUT /api/v1/media/{media_id}/tags

# Архивация
POST /api/v1/media/{media_id}/archive

# Удаление
DELETE /api/v1/media/{media_id}
```

## Интеграция с основным ботом

### Пример использования клиента

```python
from media_service.client import MediaServiceClient, BotMediaIntegration

# Инициализация клиента
media_client = MediaServiceClient(\"http://media-service:8000\")

# Интеграция с ботом
integration = BotMediaIntegration(media_client, bot)

# Обработка фото заявки
result = await integration.handle_request_photo(
    message=message,
    request_number=\"250920-001\",
    user_id=user.id,
    description=\"Повреждение трубы\",
    tags=[\"plumbing\", \"urgent\"]
)

# Получение галереи заявки
gallery = await integration.get_request_media_gallery(\"250920-001\")
```

### Быстрые функции

```python
from media_service.client import upload_request_photo, upload_completion_photo

# Загрузка фото заявки
await upload_request_photo(
    client=media_client,
    request_number=\"250920-001\",
    photo_path=\"/path/to/photo.jpg\",
    description=\"Фото проблемы\",
    uploaded_by=user_id
)

# Загрузка фото завершения
await upload_completion_photo(
    client=media_client,
    request_number=\"250920-001\",
    photo_path=\"/path/to/completion.jpg\",
    uploaded_by=user_id
)
```

## Конфигурация каналов

Сервис использует 4 приватных Telegram канала:

1. **Requests** - Медиа-файлы заявок
2. **Reports** - Фото отчетов о выполнении
3. **Archive** - Архивные файлы
4. **Backup** - Резервные копии

### Настройка каналов

1. Создайте 4 приватных канала в Telegram
2. Добавьте бота как администратора с правами:
   - Отправка сообщений
   - Редактирование сообщений
   - Удаление сообщений
3. Укажите username каналов в `.env`

## Разработка

### Структура проекта

```
app/
├── api/v1/               # API версии 1
│   ├── media.py         # Media endpoints
│   ├── health.py        # Health checks
│   └── router.py        # Main router
├── core/
│   └── config.py        # Configuration
├── db/
│   └── database.py      # Database setup
├── models/
│   └── media.py         # Database models
├── schemas/
│   └── media.py         # Pydantic schemas
└── services/
    ├── media_storage.py  # Storage service
    ├── media_search.py   # Search service
    └── telegram_client.py # Telegram API
```

### Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск базы данных
docker-compose -f docker-compose.dev.yml up -d media-db media-redis

# Запуск приложения
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Тестирование
pytest tests/ -v
```

### Работа с моделями

```python
# Создание новой миграции
alembic revision --autogenerate -m \"Add new field\"

# Применение миграций
alembic upgrade head

# Откат миграций
alembic downgrade -1
```

## Тестирование

```bash
# Запуск всех тестов
docker-compose -f docker-compose.dev.yml exec media-api pytest

# Тесты с покрытием
docker-compose -f docker-compose.dev.yml exec media-api pytest --cov=app

# Интеграционные тесты
docker-compose -f docker-compose.dev.yml exec media-api pytest tests/integration/

# Тестирование API
docker-compose -f docker-compose.dev.yml exec media-api pytest tests/api/
```

## Производство

### Развертывание

```bash
# Production build
docker-compose up -d

# Проверка состояния
docker-compose ps

# Просмотр логов
docker-compose logs -f media-api

# Обновление
docker-compose pull
docker-compose up -d --force-recreate
```

### Мониторинг

```bash
# Health check
curl http://localhost:8001/api/v1/health/detailed

# Метрики
curl http://localhost:8001/api/v1/media/statistics
```

## Безопасность

- Все медиа-файлы хранятся в приватных Telegram каналах
- Валидация типов и размеров файлов
- Rate limiting на API endpoints
- Логирование всех операций
- Использование непривилегированного пользователя в контейнере

## Ограничения

- Максимальный размер файла: 50MB (Telegram ограничение)
- Поддерживаемые форматы: JPG, PNG, GIF, MP4, PDF, DOC, DOCX
- Telegram API rate limits применяются
- Бесплатное хранилище ограничено политиками Telegram

## Лицензия

Proprietary - UK Management System

## Поддержка

Для вопросов и поддержки обращайтесь к команде разработки UK Management Bot.