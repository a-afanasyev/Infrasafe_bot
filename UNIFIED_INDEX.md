# 📚 Единое Развертывание - Навигация

**UK Management Bot + Media Service - Unified Deployment**

Версия: 1.0.0 | Дата: 15.10.2025 | Статус: ✅ Production Ready

---

## 🚀 Быстрый Доступ

### Для новых пользователей
1. **[QUICKSTART.md](QUICKSTART.md)** - Начните здесь! Запуск за 3 минуты
2. **[README.UNIFIED.md](README.UNIFIED.md)** - Полное руководство
3. **[.env.unified.example](.env.unified.example)** - Пример конфигурации

### Для разработчиков
1. **[UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md)** - Детальная документация
2. **[Makefile](Makefile)** - Все команды (выполните `make help`)
3. **[docker-compose.unified.yml](docker-compose.unified.yml)** - Конфигурация Docker

### Для DevOps
1. **[UNIFIED_SUMMARY.md](UNIFIED_SUMMARY.md)** - Резюме и чек-листы
2. **Скрипты управления** - См. раздел ниже
3. **Production deployment** - См. [UNIFIED_DEPLOYMENT.md#Production](UNIFIED_DEPLOYMENT.md)

---

## 📁 Структура Файлов

### Основные файлы конфигурации

```
docker-compose.unified.yml     Главный Docker Compose файл
├── 5 сервисов (bot, media-service, media-frontend, postgres, redis)
├── 3 volumes (postgres_data, redis_data, media_uploads)
└── 1 network (uk-network)

Makefile                       Команды управления
├── 50+ команд
├── Управление сервисами
├── Тестирование
├── Backup/Restore
└── Отладка

.env                          Переменные окружения (создайте из примера)
.env.unified.example          Пример конфигурации со всеми переменными
```

### Скрипты управления

| Скрипт | Назначение | Использование |
|--------|-----------|---------------|
| [start-unified.sh](start-unified.sh) | Запуск всех сервисов | `./start-unified.sh` |
| [stop-unified.sh](stop-unified.sh) | Остановка сервисов | `./stop-unified.sh` |
| [restart-unified.sh](restart-unified.sh) | Перезапуск сервисов | `./restart-unified.sh [service]` |
| [logs-unified.sh](logs-unified.sh) | Просмотр логов | `./logs-unified.sh [service]` |
| [test-media-service.sh](test-media-service.sh) | Тест Media Service | `./test-media-service.sh` |

### Документация

| Файл | Размер | Описание |
|------|--------|----------|
| [README.UNIFIED.md](README.UNIFIED.md) | 15K | **Главное руководство** - Начните здесь! |
| [QUICKSTART.md](QUICKSTART.md) | 4.4K | **Быстрый старт** - Запуск за 3 минуты |
| [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | 14K | **Полная документация** - Все детали |
| [UNIFIED_SUMMARY.md](UNIFIED_SUMMARY.md) | 11K | **Резюме** - Чек-листы и примеры |
| [UNIFIED_INDEX.md](UNIFIED_INDEX.md) | - | **Этот файл** - Навигация |

---

## 🎯 Сценарии использования

### Сценарий 1: Первый запуск (новый пользователь)

```bash
# 1. Читаем быстрый старт
cat QUICKSTART.md

# 2. Инициализация
make init

# 3. Настройка
cp .env.unified.example .env
nano .env  # Установите BOT_TOKEN

# 4. Запуск
make start

# 5. Проверка
make status
make health

# 6. Тестирование
make test-media
open http://localhost:8010
```

**Документация**: [QUICKSTART.md](QUICKSTART.md)

---

### Сценарий 2: Ежедневная разработка

```bash
# Утро - запуск
make start

# Проверка статуса
make status

# Просмотр логов (в отдельном терминале)
make logs-bot

# Разработка - код автоматически обновляется
# Изменения в uk_management_bot/ или media_service/app/

# При необходимости перезапуск
make restart-bot

# Тестирование
make test

# Вечер - остановка
make stop
```

**Документация**: [README.UNIFIED.md](README.UNIFIED.md)

---

### Сценарий 3: Отладка проблемы

```bash
# 1. Проверка статуса
make status

# 2. Healthcheck
make health

# 3. Логи с ошибками
make logs-bot | grep -i error | tail -50
make logs-media | grep -i error | tail -50

# 4. Детальные логи конкретного сервиса
make logs-bot      # Бот
make logs-media    # Media Service
make logs-db       # PostgreSQL
make logs-redis    # Redis

# 5. Shell доступ для отладки
make shell-bot     # Bash в контейнере бота
make shell-media   # Sh в контейнере Media Service
make shell-db      # PostgreSQL CLI
make shell-redis   # Redis CLI

# 6. Перезапуск проблемного сервиса
make restart-bot
make restart-media

# 7. Полный перезапуск
make restart
```

**Документация**: [UNIFIED_DEPLOYMENT.md#Отладка](UNIFIED_DEPLOYMENT.md)

---

### Сценарий 4: Тестирование нового функционала

```bash
# 1. Запуск тестов бота
make test

# 2. Тестирование Media Service API
make test-media

# 3. Ручное тестирование API
curl http://localhost:8009/api/v1/health
curl http://localhost:8009/api/v1/channels | jq

# 4. Загрузка тестового файла
curl -X POST "http://localhost:8009/api/v1/media/upload" \
  -F "file=@test.jpg" \
  -F "channel_id=photos"

# 5. Веб-интерфейс для тестирования
open http://localhost:8010

# 6. API документация
open http://localhost:8009/docs
```

**Документация**: [UNIFIED_DEPLOYMENT.md#Тестирование](UNIFIED_DEPLOYMENT.md)

---

### Сценарий 5: Backup и восстановление

```bash
# Создание backup
make backup-db

# Список backups
ls -lh backups/

# Восстановление из backup
make restore-db FILE=backups/backup_20241015_120000.sql

# Backup медиа файлов (опционально)
docker run --rm \
  -v uk_media_uploads:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/media_backup_$(date +%Y%m%d).tar.gz /data
```

**Документация**: [UNIFIED_DEPLOYMENT.md#Backup](UNIFIED_DEPLOYMENT.md)

---

### Сценарий 6: Production Deployment

```bash
# 1. Подготовка .env для production
cp .env .env.production
nano .env.production  # Настроить для production

# 2. Изменить параметры
DEBUG=false
LOG_LEVEL=WARNING
CORS_ENABLED=false

# 3. Использовать production compose
docker-compose -f docker-compose.prod.yml up -d

# 4. Проверка
docker-compose -f docker-compose.prod.yml ps
curl http://localhost:8009/api/v1/health

# 5. Настроить Nginx reverse proxy
# См. UNIFIED_DEPLOYMENT.md#Production

# 6. Настроить SSL
certbot --nginx -d api.yourdomain.com

# 7. Мониторинг
make status
make health
```

**Документация**: [UNIFIED_DEPLOYMENT.md#Production](UNIFIED_DEPLOYMENT.md)

---

## 📋 Команды Make (Top 20)

### Управ��ение сервисами
```bash
make start              # Запустить все сервисы
make stop               # Остановить все сервисы
make restart            # Перезапустить все сервисы
make restart-bot        # Перезапустить только бота
make restart-media      # Перезапустить только Media Service
```

### Мониторинг
```bash
make status             # Статус всех сервисов
make health             # Healthcheck всех сервисов
make logs               # Логи всех сервисов
make logs-bot           # Логи бота
make logs-media         # Логи Media Service
make top                # Процессы в контейнерах
make stats              # Использование ресурсов
```

### Тестирование
```bash
make test               # Запустить все тесты
make test-media         # Тестировать Media Service
```

### Отладка
```bash
make shell-bot          # Shell в контейнере бота
make shell-media        # Shell в контейнере Media Service
make shell-db           # PostgreSQL CLI
make shell-redis        # Redis CLI
```

### Обслуживание
```bash
make backup-db          # Backup PostgreSQL
make clean              # Очистить Docker
make build              # Пересобрать образы
```

### Справка
```bash
make help               # Показать все команды (50+)
```

---

## 🌐 Endpoints и Порты

### Внешние сервисы (доступны с хоста)

| Сервис | URL | Порт | Описание |
|--------|-----|------|----------|
| **Media Service API** | http://localhost:8009 | 8009 | REST API |
| **API Documentation** | http://localhost:8009/docs | 8009 | Swagger UI |
| **Media Frontend** | http://localhost:8010 | 8010 | Web Interface |
| **PostgreSQL** | localhost:5432 | 5432 | Database |
| **Redis** | localhost:6379 | 6379 | Cache |

### Внутренние сервисы (только внутри Docker)

| Сервис | URL | Описание |
|--------|-----|----------|
| **Bot Healthcheck** | http://bot:8000/health | Healthcheck бота |
| **Media Service (internal)** | http://media-service:8000 | Внутренний URL |

### API Endpoints

**Media Service API:**
```
GET  /api/v1/health          - Healthcheck
GET  /api/v1/channels        - Список каналов
POST /api/v1/media/upload    - Загрузка файла
GET  /api/v1/media/{id}      - Информация о файле
GET  /api/v1/media/{id}/url  - URL для скачивания
GET  /api/v1/cache/stats     - Статистика кеша
GET  /docs                   - API документация
```

---

## 🔧 Конфигурация

### Минимальная (.env)
```bash
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789
DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management
REDIS_URL=redis://redis:6379/0
```

### Рекомендуемая (см. .env.unified.example)
```bash
# Telegram
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789,987654321

# Database
DATABASE_URL=postgresql://uk_bot:uk_bot_password@postgres:5432/uk_management

# Redis
REDIS_URL=redis://redis:6379/0
USE_REDIS_RATE_LIMIT=true

# Media Service
MEDIA_SERVICE_URL=http://media-service:8000
MAX_FILE_SIZE=52428800
ALLOWED_EXTENSIONS=jpg,jpeg,png,gif,mp4,mov,avi,pdf,doc,docx

# Logging
LOG_LEVEL=INFO
DEBUG=false

# Features
SHIFTS_ENABLED=true
AI_ASSIGNMENT_ENABLED=true
```

**Полный пример**: [.env.unified.example](.env.unified.example)

---

## 📊 Архитектура

### Компоненты системы

```
┌─────────────────────────────────────────────────────┐
│              UK Management System                    │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐      ┌──────────────────┐         │
│  │ Telegram Bot│◄────►│  Media Service   │         │
│  │  (Aiogram)  │      │    (FastAPI)     │         │
│  │             │      │                  │         │
│  │  Port: -    │      │  Port: 8009      │         │
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
│  │  • ...                           │               │
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
│  │  Static HTML + JS test interface │               │
│  └──────────────────────────────────┘               │
│                                                       │
└─────────────────────────────────────────────────────┘

External Services:
┌──────────────────┐
│ Telegram API     │
│ Bot API Server   │
└──────────────────┘
```

### Docker Volumes

```
postgres_data       → PostgreSQL database files
redis_data          → Redis persistence files
media_uploads       → Uploaded media files
```

### Docker Networks

```
uk-network (bridge)
  ├── bot
  ├── media-service
  ├── media-frontend
  ├── postgres
  └── redis
```

---

## ✨ Особенности

### ✅ Единое управление
- Один Docker Compose файл для всех сервисов
- Автоматическое управление зависимостями
- Healthcheck для каждого сервиса

### ✅ Удобная разработка
- Hot-reload для бота и Media Service
- Volume mapping для кода
- Не требуется пересборка при изменениях

### ✅ 50+ команд Make
- Управление сервисами
- Логи и мониторинг
- Тестирование
- Backup/Restore
- Отладка

### ✅ Полная документация
- Быстрый старт
- Детальное руководство
- Примеры использования
- FAQ и решение проблем

### ✅ Production Ready
- Healthcheck для всех сервисов
- Правильная обработка зависимостей
- Persistence для данных
- Безопасная конфигурация

---

## 🆘 Помощь

### Быстрые ответы

**Q: Как начать?**
A: Читайте [QUICKSTART.md](QUICKSTART.md)

**Q: Не могу запустить**
A: `make health` → проверьте логи → [UNIFIED_DEPLOYMENT.md#Отладка](UNIFIED_DEPLOYMENT.md)

**Q: Порт занят**
A: `lsof -i :8009` → остановите процесс

**Q: Где логи?**
A: `make logs` или `make logs-bot` или `make logs-media`

**Q: Как обновить код?**
A: Просто сохраните файл - hot-reload применит изменения

**Q: Как сделать backup?**
A: `make backup-db`

### Документация по темам

| Тема | Документ | Раздел |
|------|----------|--------|
| Быстрый старт | [QUICKSTART.md](QUICKSTART.md) | Все |
| Установка | [README.UNIFIED.md](README.UNIFIED.md) | Quick Start |
| Команды | [Makefile](Makefile) | `make help` |
| Конфигурация | [.env.unified.example](.env.unified.example) | Все |
| Архитектура | [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | Архитектура |
| Тестирование | [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | Тестирование |
| Отладка | [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | Отладка |
| Production | [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | Production |
| FAQ | [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md) | FAQ |
| Резюме | [UNIFIED_SUMMARY.md](UNIFIED_SUMMARY.md) | Все |

---

## 📞 Контакты и Поддержка

### Команды для самопомощи
```bash
make help           # Все команды
make status         # Статус сервисов
make health         # Проверка здоровья
make logs           # Логи
```

### GitHub Issues
Создайте issue с:
- Описанием проблемы
- Выводом `make status`
- Логами `make logs-bot` / `make logs-media`
- Версией Docker: `docker --version`

---

## 📝 История изменений

### v1.0.0 (15.10.2025)
- ✅ Создан единый Docker Compose файл
- ✅ Добавлен Makefile с 50+ командами
- ✅ Созданы скрипты управления (start, stop, restart, logs, test)
- ✅ Написана полная документация (15K слов)
- ✅ Добавлены примеры конфигурации
- ✅ Реализован hot-reload для разработки
- ✅ Настроены healthcheck для всех сервисов
- ✅ Протестирована работоспособность

---

## ✅ Чек-лист готовности

### Перед первым запуском
- [ ] Docker и Docker Compose установлены
- [ ] Порты 5432, 6379, 8009, 8010 свободны
- [ ] Создан .env файл (из .env.unified.example)
- [ ] BOT_TOKEN установлен в .env
- [ ] ADMIN_IDS установлен в .env
- [ ] Минимум 2GB RAM доступно

### После запуска
- [ ] `make status` показывает все сервисы Up (healthy)
- [ ] `make health` проходит успешно
- [ ] http://localhost:8009/api/v1/health возвращает success
- [ ] http://localhost:8010 открывается
- [ ] Бот отвечает в Telegram

---

**Версия**: 1.0.0
**Дата**: 15 октября 2025
**Статус**: ✅ Production Ready

**Начните с**: [QUICKSTART.md](QUICKSTART.md)
