# 🚀 UK Management Bot - Единое Развертывание

> **Telegram Bot + Media Service в одном Docker Compose файле**

[![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-teal.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)

---

## 📋 Что это?

Единое Docker Compose окружение для запуска:
- ✅ **Telegram Bot** - UK Management Bot для управления заявками
- ✅ **Media Service** - FastAPI сервис для загрузки и хранения медиа
- ✅ **PostgreSQL** - База данных
- ✅ **Redis** - Кеш и очереди
- ✅ **Frontend** - Веб-интерфейс для тестирования

**Одна команда = всё работает!**

---

## ⚡ Быстрый Старт

### 1️⃣ Подготовка (первый раз)

```bash
# Клонировать репозиторий
git clone <your-repo>
cd UK

# Инициализация
make init

# Настроить .env
nano .env
# Установите BOT_TOKEN и другие параметры
```

### 2️⃣ Запуск

```bash
# Вариант 1: Через скрипт
./start-unified.sh

# Вариант 2: Через Make
make start

# Вариант 3: Напрямую через Docker Compose
docker-compose -f docker-compose.unified.yml up -d
```

### 3️⃣ Проверка

```bash
# Статус сервисов
make status

# Healthcheck
make health

# Логи
make logs
```

**Готово!** 🎉

---

## 🌐 Доступные Сервисы

После запуска доступны:

| Сервис | URL | Описание |
|--------|-----|----------|
| **Media Service API** | http://localhost:8009 | REST API для медиа |
| **Media API Docs** | http://localhost:8009/docs | Swagger документация |
| **Media Frontend** | http://localhost:8010 | Веб-интерфейс для загрузки |
| **PostgreSQL** | localhost:5432 | База данных |
| **Redis** | localhost:6379 | Кеш и очереди |
| **Telegram Bot** | - | Через Telegram API |

---

## 📚 Команды Make

```bash
make help              # Показать все команды
make start             # Запустить все сервисы
make stop              # Остановить все сервисы
make restart           # Перезапустить все сервисы
make logs              # Показать логи
make status            # Статус сервисов
make health            # Проверить здоровье
make test              # Запустить тесты
make clean             # Очистить Docker
make backup-db         # Backup PostgreSQL
make shell-bot         # Shell в контейнере бота
make shell-db          # PostgreSQL CLI
```

**Полный список**: `make help`

---

## 🛠️ Управление Сервисами

### Просмотр логов

```bash
# Все сервисы
make logs

# Конкретный сервис
make logs-bot          # Бот
make logs-media        # Media Service
make logs-db           # PostgreSQL
make logs-redis        # Redis
```

### Перезапуск

```bash
# Все сервисы
make restart

# Конкретный сервис
make restart-bot       # Только бот
make restart-media     # Только Media Service
```

### Остановка

```bash
# Остановить
make stop

# Остановить + удалить volumes (ОСТОРОЖНО!)
make down-v
```

---

## 🧪 Тестирование

### Автоматические тесты

```bash
# Все тесты
make test

# Тесты бота
docker-compose -f docker-compose.unified.yml exec bot pytest

# Тесты Media Service
docker-compose -f docker-compose.unified.yml exec media-service pytest
```

### Тестирование Media Service

```bash
# Через скрипт
./test-media-service.sh

# Через Make
make test-media

# Вручную
curl http://localhost:8009/api/v1/health
curl http://localhost:8009/api/v1/channels | jq
```

### Загрузка тестового файла

```bash
curl -X POST "http://localhost:8009/api/v1/media/upload" \
  -F "file=@photo.jpg" \
  -F "channel_id=photos"
```

Или откройте http://localhost:8010

---

## 🔍 Отладка

### Проверка статуса

```bash
# Статус контейнеров
make status

# Healthcheck
make health

# Процессы в контейнерах
make top

# Использование ресурсов
make stats
```

### Логи с ошибками

```bash
# Последние ошибки бота
make logs-bot | grep -i error | tail -50

# Последние ошибки Media Service
make logs-media | grep -i error | tail -50
```

### Shell доступ

```bash
# Bot container
make shell-bot

# Media Service container
make shell-media

# PostgreSQL CLI
make shell-db

# Redis CLI
make shell-redis
```

---

## 💾 Backup и восстановление

### Backup базы данных

```bash
# Создать backup
make backup-db

# Файл сохраняется в: backups/backup_YYYYMMDD_HHMMSS.sql
```

### Восстановление

```bash
# Восстановить из backup
make restore-db FILE=backups/backup_20241015_120000.sql
```

---

## 🔧 Конфигурация

### Структура файлов

```
UK/
├── docker-compose.unified.yml    # Docker Compose конфигурация
├── Makefile                      # Make команды
├── .env                          # Переменные окружения
├── .env.unified.example          # Пример конфигурации
│
├── start-unified.sh              # Скрипт запуска
├── stop-unified.sh               # Скрипт остановки
├── logs-unified.sh               # Скрипт логов
├── restart-unified.sh            # Скрипт перезапуска
├── test-media-service.sh         # Тестирование Media Service
│
├── QUICKSTART.md                 # Краткое руководство
├── UNIFIED_DEPLOYMENT.md         # Полная документация
├── README.UNIFIED.md             # Этот файл
│
├── uk_management_bot/            # Код бота
├── media_service/                # Код Media Service
│   ├── app/                      # FastAPI приложение
│   ├── frontend/                 # Веб-интерфейс
│   └── channels.json             # Каналы для загрузки
│
└── scripts/                      # Вспомогательные скрипты
```

### Переменные окружения

Основные переменные в `.env`:

```bash
# Обязательные
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789

# База данных
DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management

# Redis
REDIS_URL=redis://redis:6379/0

# Media Service
MEDIA_SERVICE_URL=http://media-service:8000
MAX_FILE_SIZE=52428800
```

**Полный пример**: `.env.unified.example`

---

## 📊 Архитектура

```
┌─────────────────────────────────────────────────────┐
│              UK Management System                    │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐      ┌──────────────────┐         │
│  │ Telegram Bot│◄────►│  Media Service   │         │
│  │  (Aiogram)  │      │    (FastAPI)     │         │
│  │             │      │                  │         │
│  │  Handlers   │      │  API Endpoints   │         │
│  │  Services   │      │  File Storage    │         │
│  │  FSM States │      │  Telegram Upload │         │
│  └──────┬──────┘      └────────┬─────────┘         │
│         │                      │                     │
│         │    ┌─────────────────┘                     │
│         ▼    ▼                                       │
│  ┌──────────────────────────────────┐               │
│  │       PostgreSQL Database        │               │
│  │          Port: 5432              │               │
│  │                                  │               │
│  │  Tables:                         │               │
│  │  • users                         │               │
│  │  • requests                      │               │
│  │  • shifts                        │               │
│  │  • media_files                   │               │
│  └──────────────────────────────────┘               │
│                                                       │
│  ┌──────────────────────────────────┐               │
│  │          Redis Cache             │               │
│  │          Port: 6379              │               │
│  │                                  │               │
│  │  DB 0: Bot cache & sessions      │               │
│  │  DB 1: Media Service cache       │               │
│  └──────────────────────────────────┘               │
│                                                       │
│  ┌──────────────────────────────────┐               │
│  │      Media Frontend (Nginx)      │               │
│  │          Port: 8010              │               │
│  │  Test upload interface           │               │
│  └──────────────────────────────────┘               │
│                                                       │
└─────────────────────────────────────────────────────┘

External:
┌──────────────────┐
│ Telegram API     │
│ Bot API Server   │
└──────────────────┘
```

---

## 🚀 Production Deployment

### Подготовка к production

1. **Обновите .env**
   ```bash
   DEBUG=false
   LOG_LEVEL=WARNING
   CORS_ENABLED=false
   ```

2. **Используйте production compose**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

3. **Настройте Nginx reverse proxy**
   ```nginx
   server {
       listen 80;
       server_name api.yourdomain.com;

       location / {
           proxy_pass http://localhost:8009;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

4. **Настройте SSL**
   ```bash
   certbot --nginx -d api.yourdomain.com
   ```

5. **Настройте мониторинг**
   - Prometheus для метрик
   - Grafana для дашбордов
   - Alertmanager для уведомлений

---

## 🛡️ Безопасность

### Чек-лист безопасности

- ✅ Используйте сильные пароли для PostgreSQL
- ✅ Сгенерируйте уникальный SECRET_KEY
- ✅ Ограничьте ADMIN_IDS только доверенными ID
- ✅ Отключите DEBUG в production
- ✅ Используйте HTTPS для API
- ✅ Настройте firewall для портов
- ✅ Регулярно обновляйте Docker образы
- ✅ Делайте backup базы данных

### Генерация секретов

```bash
# SECRET_KEY
openssl rand -hex 32

# PostgreSQL пароль
openssl rand -base64 32
```

---

## 📈 Мониторинг

### Healthcheck endpoints

```bash
# Bot healthcheck
curl http://localhost:8000/health

# Media Service healthcheck
curl http://localhost:8009/api/v1/health

# PostgreSQL
docker-compose -f docker-compose.unified.yml exec postgres pg_isready

# Redis
docker-compose -f docker-compose.unified.yml exec redis redis-cli ping
```

### Метрики

```bash
# Статистика кеша
curl http://localhost:8009/api/v1/cache/stats | jq

# Использование ресурсов
docker stats
```

---

## ❓ FAQ

**Q: Порт 8009 уже занят**
A: Измените в `docker-compose.unified.yml` или остановите процесс на порту

**Q: Бот не отвечает**
A: Проверьте BOT_TOKEN в .env и логи: `make logs-bot`

**Q: Ошибка подключения к БД**
A: Убедитесь что PostgreSQL запущен: `make status`

**Q: Media Service не загружает файлы**
A: Проверьте права на директорию: `ls -la media_service/data/uploads`

**Q: Как обновить код без перезапуска?**
A: Изменения кода применяются автоматически благодаря volume mapping

**Q: Как очистить все данные?**
A: `make down-v` (ВНИМАНИЕ: удалит все данные!)

---

## 🤝 Поддержка

### Документация

- **Краткое руководство**: [QUICKSTART.md](QUICKSTART.md)
- **Полная документация**: [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md)
- **Проект**: [CLAUDE.md](CLAUDE.md)

### Помощь

```bash
# Справка по командам
make help

# Проверка здоровья
make health

# Просмотр логов
make logs

# Статус сервисов
make status
```

---

## 📝 Changelog

### v1.0.0 (2025-10-15)
- ✅ Единый Docker Compose файл
- ✅ Makefile с удобными командами
- ✅ Автоматические скрипты управления
- ✅ Healthcheck для всех сервисов
- ✅ Тестовый веб-интерфейс
- ✅ Полная документация

---

## 📄 Лицензия

См. LICENSE файл

---

## 👥 Авторы

UK Management Bot Team

---

**Версия**: 1.0.0
**Обновлено**: 15 октября 2025
**Статус**: ✅ Production Ready

**🚀 Счастливого развертывания!**
