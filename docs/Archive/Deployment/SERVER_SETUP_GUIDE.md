# 🚀 Руководство по развертыванию на сервере

> _Последнее редактирование: 2026-05-30_

## Быстрый старт

### 1. Подготовка сервера

```bash
# Добавить пользователя в группу docker (чтобы не нужен был sudo)
sudo usermod -aG docker $USER

# Перелогиниться для применения изменений
exit
# Зайдите снова по SSH
```

### 2. Клонирование репозитория

```bash
cd ~
git clone https://github.com/a-afanasyev/Infrasafe_bot.git
cd Infrasafe_bot
```

### 3. Настройка .env файла

```bash
# Скопировать пример
cp .env.unified.example .env

# Редактировать файл
nano .env
```

### 4. ⚠️ ВАЖНО: Настройка DATABASE_URL с паролем содержащим спецсимволы

**Проблема**: Если ваш пароль содержит `@`, `$`, `#`, `:` или другие спецсимволы, Docker Compose может неправильно его интерпретировать.

**Решение 1: URL-encoding паролей**

Если пароль `Example@Pw$`, закодируйте его:
- `@` → `%40`
- `$` → `%24`
- `#` → `%23`
- `:` → `%3A`
- `/` → `%2F`

```bash
# Пример: пароль Example@Pw$ становится Example%40Pw%24
DATABASE_URL=postgresql://uk_bot:Example%40Pw%24@postgres:5432/uk_management
```

**Решение 2: Использование простого пароля (рекомендуется для начала)**

```bash
# .env файл
POSTGRES_PASSWORD=MySecurePassword123

# DATABASE_URL должен использовать тот же пароль
DATABASE_URL=postgresql://uk_bot:MySecurePassword123@postgres:5432/uk_management
```

### 5. Пример правильного .env файла

```bash
# ==================== ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ ====================
# Токен основного UK Management бота
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Токен Media Service бота (отдельный бот!)
MEDIA_BOT_TOKEN=9876543210:ZYXwvuTSRqponMLKjihGFEdcba

# ==================== DATABASE ====================
# Используйте один и тот же пароль в обоих местах!
POSTGRES_PASSWORD=MySecurePassword123
DATABASE_URL=postgresql://uk_bot:MySecurePassword123@postgres:5432/uk_management

# Database settings
POSTGRES_DB=uk_management
POSTGRES_USER=uk_bot

# ==================== REDIS ====================
REDIS_URL=redis://redis:6379/0
MEDIA_REDIS_URL=redis://redis:6379/1
USE_REDIS_RATE_LIMIT=true

# ==================== MEDIA CHANNELS (опционально) ====================
# ID Telegram каналов для хранения медиа
# Значения по умолчанию уже настроены, изменяйте только если нужны свои каналы
CHANNEL_REQUESTS=-1003091883002
CHANNEL_REPORTS=-1002969942316
CHANNEL_ARCHIVE=-1002725515580
CHANNEL_BACKUP=-1002951349061

# ==================== ОСТАЛЬНЫЕ ПАРАМЕТРЫ ====================
LOG_LEVEL=INFO
DEBUG=false
```

### 6. Запуск

```bash
# Первый запуск (без sudo если вы в группе docker)
make start

# Проверка логов
make logs

# Проверка статуса
make ps

# Проверка здоровья
make health
```

### 7. Проверка запуска

```bash
# Проверить что все контейнеры запущены
docker ps

# Должны быть запущены:
# - uk-bot
# - uk-media-service
# - uk-media-frontend
# - uk-postgres
# - uk-redis

# Проверить логи бота
docker logs uk-bot

# Проверить healthcheck
curl http://localhost:8009/api/v1/health
```

## 🔍 Диагностика проблем

### Ошибка: "telegram_bot_token Field required"

**Причина**: Не установлен MEDIA_BOT_TOKEN для Media Service.

**Решение**:
```bash
# В .env файле добавьте:
MEDIA_BOT_TOKEN=your_media_bot_token_here
```

**Важно**: Нужно создать **два отдельных бота**:
1. UK Management Bot - основной бот (BOT_TOKEN)
2. Media Service Bot - бот для медиа (MEDIA_BOT_TOKEN)

Оба токена получите у @BotFather в Telegram.

### Ошибка: "The 'afe' variable is not set"

**Причина**: Пароль вида `Example@Pw$` содержит `$…`, который Docker воспринимает как переменную.

**Решение**:
1. Используйте URL-encoding: `Example%40Pw%24`
2. Или измените пароль на простой без `$`

### Ошибка: "dependency failed to start: container uk-postgres is unhealthy"

**Причина**: PostgreSQL не может запуститься или healthcheck падает.

**Проверка**:
```bash
# Проверить логи PostgreSQL
docker logs uk-postgres

# Проверить что пароли совпадают
grep POSTGRES_PASSWORD .env
grep DATABASE_URL .env

# Пересоздать контейнеры
make clean
make start
```

### Ошибка: "permission denied while trying to connect to the Docker daemon"

**Причина**: Пользователь не в группе docker.

**Решение**:
```bash
sudo usermod -aG docker $USER
# Перелогиниться!
exit
```

### Проверка что .env файл загружен правильно

```bash
# Проверить переменные в контейнере
docker exec uk-bot env | grep DATABASE_URL
docker exec uk-postgres env | grep POSTGRES_PASSWORD
```

## 🛡️ Security для Production

### 1. Измените все пароли

```bash
# Генерация безопасного пароля
openssl rand -base64 32

# Используйте пароль БЕЗ спецсимволов для простоты
# Например: a8Kf9mN2pQ4rT6vX8yZ1bC3dE5fG7hJ9
```

### 2. Закройте порты БД

```bash
# Отредактируйте docker-compose.unified.yml
nano docker-compose.unified.yml

# Закомментируйте секции:
# postgres:
#   ports:
#     - "5432:5432"  # <-- Закомментируйте эту строку
#
# redis:
#   ports:
#     - "6379:6379"  # <-- И эту
```

### 3. Измените LOG_LEVEL на INFO

```bash
# В .env файле
LOG_LEVEL=INFO
DEBUG=false
```

## 📋 Makefile команды

```bash
make start          # Запустить все сервисы
make stop           # Остановить все сервисы
make restart        # Перезапустить все сервисы
make logs           # Показать логи всех сервисов
make logs-bot       # Показать логи только бота
make ps             # Показать статус контейнеров
make health         # Проверить здоровье сервисов
make clean          # Остановить и удалить контейнеры
make rebuild        # Пересобрать и перезапустить
make backup-db      # Создать backup БД
```

## 🎯 Checklist для первого запуска

- [ ] Пользователь добавлен в группу docker
- [ ] Создан .env файл из .env.unified.example
- [ ] BOT_TOKEN установлен (основной бот, получен у @BotFather)
- [ ] MEDIA_BOT_TOKEN установлен (медиа бот, получен у @BotFather)
- [ ] POSTGRES_PASSWORD установлен (БЕЗ спецсимволов)
- [ ] DATABASE_URL использует тот же пароль
- [ ] `make start` выполняется без ошибок
- [ ] Все 5 контейнеров запущены (`docker ps`)
- [ ] Healthcheck проходит (`make health`)
- [ ] Оба бота отвечают в Telegram

## 🔄 Обновление кода

```bash
cd ~/Infrasafe_bot
git pull
make restart
```

## 📞 Если ничего не помогает

1. Полная очистка и пересборка:
```bash
make clean
docker system prune -a --volumes  # ВНИМАНИЕ: удалит ВСЕ данные!
make start
```

2. Проверить логи каждого сервиса:
```bash
docker logs uk-postgres
docker logs uk-redis
docker logs uk-bot
docker logs uk-media-service
docker logs uk-media-frontend
```

3. Проверить что .env файл правильный:
```bash
cat .env | grep -v "^#" | grep -v "^$"
```

---

**Создано**: 15 октября 2025
**Версия**: 1.0
**Репозиторий**: https://github.com/a-afanasyev/Infrasafe_bot
