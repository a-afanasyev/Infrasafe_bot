# 🐳 Docker Setup для UK Management Bot

## 📋 Обзор

Этот документ содержит подробные инструкции по настройке и запуску UK Management Bot в Docker контейнерах. Система включает:

- **Основное приложение** (Telegram бот)
- **База данных** (PostgreSQL для production или SQLite для development)
- **Redis** (кэширование и rate limiting)

## 🎯 Выбор конфигурации

### 🚀 Production (PostgreSQL) - Рекомендуется
```bash
# Полная конфигурация с PostgreSQL
docker-compose up -d
```

**Преимущества:**
- ✅ Многопользовательская поддержка
- ✅ ACID compliance
- ✅ Лучшая производительность при нагрузке
- ✅ Готовность к масштабированию
- ✅ Production-ready

### 🛠️ Development (SQLite) - Для разработки
```bash
# Упрощенная конфигурация с SQLite
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

**Преимущества:**
- ✅ Простая настройка
- ✅ Меньше ресурсов
- ✅ Быстрый старт
- ✅ Подходит для разработки
- ✅ Соответствует текущей конфигурации проекта

## 🚀 Быстрый старт

### 1. Подготовка окружения

```bash
# Клонируйте репозиторий (если еще не сделали)
git clone <your-repo-url>
cd UK

# Убедитесь, что Docker и Docker Compose установлены
docker --version
docker-compose --version
```

### 2. Настройка переменных окружения

#### Для Production (PostgreSQL):
```bash
# Скопируйте пример конфигурации
cp env.example .env

# Отредактируйте .env файл с вашими настройками
nano .env
```

#### Для Development (SQLite):
```bash
# Скопируйте development конфигурацию
cp env.dev.example .env

# Отредактируйте .env файл с вашими настройками
nano .env
```

**ВАЖНО**: Обязательно измените следующие параметры в `.env`:

```bash
# Telegram Bot Token (получить у @BotFather)
BOT_TOKEN=ваш_реальный_токен_бота

# Сгенерируйте безопасные пароли
ADMIN_PASSWORD=$(openssl rand -base64 32)
INVITE_SECRET=$(openssl rand -base64 64)

# Telegram ID администраторов
ADMIN_USER_IDS=ваш_telegram_id,id_другого_админа
```

### 3. Запуск системы

#### Production (PostgreSQL):
```bash
# Собрать и запустить все сервисы
docker-compose up -d

# Проверить статус сервисов
docker-compose ps

# Посмотреть логи приложения
docker-compose logs app
```

#### Development (SQLite):
```bash
# Собрать и запустить с SQLite
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Проверить статус сервисов
docker-compose ps

# Посмотреть логи приложения
docker-compose logs app
```

### 4. Проверка работоспособности

#### Production (PostgreSQL):
```bash
# Проверить health check приложения
docker-compose exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"

# Проверить подключение к базе данных
docker-compose exec postgres pg_isready -U uk_bot -d uk_management

# Проверить подключение к Redis
docker-compose exec redis redis-cli ping
```

#### Development (SQLite):
```bash
# Проверить health check приложения
docker-compose exec app python -c "import requests; print(requests.get('http://localhost:8000/health').json())"

# Проверить подключение к SQLite
docker-compose exec app python -c "import sqlite3; sqlite3.connect('/app/uk_management.db')"

# Проверить подключение к Redis
docker-compose exec redis redis-cli ping
```

## 🔧 Детальная настройка

### Структура файлов

```
UK/
├── Dockerfile                 # Образ приложения
├── docker-compose.yml         # Основная конфигурация сервисов
├── docker-compose.dev.yml     # Development конфигурация (SQLite)
├── docker-compose.media.yml   # Override: media-service (прод)
├── .dockerignore             # Исключения для Docker
├── env.example               # Пример переменных окружения (PostgreSQL)
├── env.dev.example           # Пример переменных окружения (SQLite)
├── .env                      # Ваши переменные окружения
├── uk_management_bot/        # Код приложения
└── DOCKER_SETUP.md          # Этот файл
```

### Сравнение конфигураций

| Аспект | Production (PostgreSQL) | Development (SQLite) |
|--------|------------------------|---------------------|
| **База данных** | PostgreSQL | SQLite |
| **Сложность** | Средняя | Простая |
| **Ресурсы** | Больше | Меньше |
| **Производительность** | Высокая | Средняя |
| **Масштабируемость** | Отличная | Ограниченная |
| **Настройка** | Требует PostgreSQL | Автоматическая |
| **Подходит для** | Production, тестирование | Разработка, демо |

### Переменные окружения

Основные переменные в `.env` файле:

| Переменная | Описание | Обязательная |
|------------|----------|--------------|
| `BOT_TOKEN` | Telegram Bot Token | ✅ |
| `ADMIN_PASSWORD` | Пароль администратора | ✅ |
| `INVITE_SECRET` | Секрет для инвайт-токенов | ✅ |
| `ADMIN_USER_IDS` | ID администраторов | ✅ |
| `DATABASE_URL` | URL базы данных | ✅ (авто) |
| `REDIS_URL` | URL Redis | ✅ (авто) |
| `LOG_LEVEL` | Уровень логирования | ❌ |
| `DEBUG` | Режим отладки | ❌ |

## 🛠️ Управление контейнерами

### Основные команды

#### Production (PostgreSQL):
```bash
# Запуск всех сервисов
docker-compose up -d

# Остановка всех сервисов
docker-compose down

# Перезапуск приложения
docker-compose restart app

# Просмотр логов
docker-compose logs app
docker-compose logs postgres
docker-compose logs redis
```

#### Development (SQLite):
```bash
# Запуск с SQLite
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Остановка
docker-compose down

# Перезапуск приложения
docker-compose restart app

# Просмотр логов
docker-compose logs app
docker-compose logs redis
```

### Общие команды:
```bash
# Просмотр логов в реальном времени
docker-compose logs -f app

# Вход в контейнер приложения
docker-compose exec app bash

# Проверка статуса сервисов
docker-compose ps
```

### Обновление приложения

```bash
# Остановить сервисы
docker-compose down

# Пересобрать образ
docker-compose build --no-cache

# Запустить снова
docker-compose up -d
```

### Резервное копирование

#### Production (PostgreSQL):
```bash
# Создать резервную копию базы данных
docker-compose exec postgres pg_dump -U uk_bot uk_management > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановить из резервной копии
docker-compose exec -T postgres psql -U uk_bot uk_management < backup_file.sql
```

#### Development (SQLite):
```bash
# Создать резервную копию SQLite файла
cp uk_management.db backup_$(date +%Y%m%d_%H%M%S).db

# Восстановить из резервной копии
cp backup_file.db uk_management.db
```

## 🔍 Мониторинг и диагностика

### Health Checks

Система автоматически проверяет состояние сервисов:

```bash
# Проверить health status
docker-compose ps

# Ручная проверка health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/health_detailed
curl http://localhost:8000/ping
```

### Логирование

```bash
# Просмотр логов приложения
docker-compose logs app

# Просмотр логов с фильтрацией
docker-compose logs app | grep ERROR
docker-compose logs app | grep "UK Management Bot"

# Просмотр логов базы данных (только для PostgreSQL)
docker-compose logs postgres

# Просмотр логов Redis
docker-compose logs redis
```

### Производительность

```bash
# Статистика использования ресурсов
docker stats

# Информация о контейнерах
docker-compose exec app python -c "
import psutil
print(f'CPU: {psutil.cpu_percent()}%')
print(f'Memory: {psutil.virtual_memory().percent}%')
"
```

## 🚨 Устранение неполадок

### Частые проблемы

#### 1. Бот не запускается

```bash
# Проверить логи
docker-compose logs app

# Проверить переменные окружения
docker-compose exec app env | grep BOT_TOKEN

# Проверить подключение к базе данных
docker-compose exec app python -c "
from uk_management_bot.database.session import engine
print('Database connection:', engine)
"
```

#### 2. Проблемы с базой данных

**PostgreSQL:**
```bash
# Проверить статус PostgreSQL
docker-compose exec postgres pg_isready -U uk_bot

# Проверить логи PostgreSQL
docker-compose logs postgres

# Пересоздать базу данных (ВНИМАНИЕ: данные будут потеряны!)
docker-compose down -v
docker-compose up -d
```

**SQLite:**
```bash
# Проверить SQLite файл
docker-compose exec app python -c "import sqlite3; sqlite3.connect('/app/uk_management.db')"

# Пересоздать SQLite файл (ВНИМАНИЕ: данные будут потеряны!)
rm uk_management.db
docker-compose restart app
```

#### 3. Проблемы с Redis

```bash
# Проверить подключение к Redis
docker-compose exec redis redis-cli ping

# Проверить логи Redis
docker-compose logs redis

# Очистить кэш Redis
docker-compose exec redis redis-cli FLUSHALL
```

#### 4. Проблемы с сетью

```bash
# Проверить сеть Docker
docker network ls
docker network inspect uk_uk-network

# Проверить DNS
docker-compose exec app nslookup postgres
docker-compose exec app nslookup redis
```

### Отладка

```bash
# Запуск в режиме отладки
DEBUG=true docker-compose up

# Вход в контейнер для отладки
docker-compose exec app bash

# Проверка процессов в контейнере
docker-compose exec app ps aux

# Проверка сетевых соединений
docker-compose exec app netstat -tulpn
```

## 🔒 Безопасность

### Рекомендации по безопасности

1. **Измените все пароли по умолчанию**
2. **Используйте HTTPS в production**
3. **Ограничьте доступ к портам**
4. **Регулярно обновляйте образы**
5. **Мониторьте логи на предмет подозрительной активности**

### Production настройки

Для production окружения:

```bash
# Создайте отдельный .env.production
cp env.example .env.production

# Используйте production конфигурацию
docker compose -f docker-compose.yml -f docker-compose.media.yml up -d  # прод; БЕЗ --remove-orphans
```

## 📚 Дополнительные ресурсы

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)
- [Redis Docker Image](https://hub.docker.com/_/redis)
- [SQLite Documentation](https://www.sqlite.org/docs.html)

## 🆘 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker-compose logs`
2. Убедитесь, что все переменные окружения настроены
3. Проверьте подключение к интернету
4. Обратитесь к документации проекта

---

**Удачного использования UK Management Bot! 🚀**
