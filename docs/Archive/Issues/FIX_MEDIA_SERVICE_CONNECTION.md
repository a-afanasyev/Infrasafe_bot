# 🔧 Исправление подключения к Media Service

> _Последнее редактирование: 2025-10-29_

**Проблема**: Бот не может подключиться к Media Service
**Ошибка**: `Health check failed: [Errno -2] Name or service not known`

---

## 🔍 Диагностика

Бот пытается подключиться к неправильному адресу:
```
Media Service клиент инициализирован: http://host.docker.internal:8001
```

Но должен подключаться к:
```
http://media-service:8000
```

---

## ✅ Решение

### На сервере выполните:

```bash
# 1. Проверить текущее значение
grep MEDIA_SERVICE_URL .env

# 2. Если там НЕ http://media-service:8000, исправить:
nano .env

# 3. Найти строку MEDIA_SERVICE_URL и изменить на:
MEDIA_SERVICE_URL=http://media-service:8000

# 4. Сохранить (Ctrl+O, Enter, Ctrl+X)

# 5. Перезапустить сервисы:
make restart

# 6. Проверить логи:
docker logs uk-bot | grep -i "media service"
```

---

## 📋 Ожидаемый результат

После исправления в логах uk-bot должно быть:
```
INFO: Media Service клиент инициализирован: http://media-service:8000
INFO: Media Service доступен: http://media-service:8000
```

Вместо:
```
ERROR: Health check failed: [Errno -2] Name or service not known
WARNING: Бот будет работать без Media Service
```

---

## 🧪 Проверка работы Media Service

### 1. Проверить что media-service доступен внутри сети
```bash
docker exec uk-bot curl http://media-service:8000/api/v1/health
```

**Ожидаемый ответ**:
```json
{"status":"ok","service":"media-service","version":"1.0.0"}
```

### 2. Проверить что media-service слушает порт 8000
```bash
docker exec uk-media-service netstat -tlnp | grep 8000
```

**Ожидаемый вывод**:
```
tcp  0  0.0.0.0:8000  0.0.0.0:*  LISTEN  1/python
```

### 3. Проверить что сервисы в одной сети
```bash
docker network inspect infrasafe_bot_uk-network | grep -A 3 "uk-bot\|uk-media-service"
```

---

## 🎯 Правильная конфигурация

### В .env файле должно быть:

```bash
# ==================== MEDIA SERVICE ====================
# URL Media Service (внутренний Docker network)
MEDIA_SERVICE_URL=http://media-service:8000
```

### ❌ НЕПРАВИЛЬНО:
```bash
MEDIA_SERVICE_URL=http://host.docker.internal:8001  # Старое значение
MEDIA_SERVICE_URL=http://localhost:8009             # Не работает в Docker
MEDIA_SERVICE_URL=http://127.0.0.1:8009             # Не работает в Docker
```

### ✅ ПРАВИЛЬНО:
```bash
MEDIA_SERVICE_URL=http://media-service:8000  # Имя контейнера в Docker network
```

---

## 📌 Важно

1. **Не используйте localhost** - контейнеры общаются через Docker network
2. **Используйте имя контейнера** - `media-service` (из docker-compose.unified.yml)
3. **Порт 8000** - внутренний порт uvicorn (не 8009 который exposed наружу)
4. **После изменения .env** - обязательно перезапустите: `make restart`

---

## 🔄 Альтернативное решение

Если не хотите редактировать .env, можно пересоздать файл:

```bash
# Удалить старый .env
rm .env

# Скопировать из примера
cp .env.unified.example .env

# Настроить только обязательные параметры:
nano .env
# Установить:
# - BOT_TOKEN=ваш_токен
# - MEDIA_BOT_TOKEN=ваш_медиа_токен
# - POSTGRES_PASSWORD=ваш_пароль
# - DATABASE_URL=postgresql://uk_bot:ваш_пароль@postgres:5432/uk_management

# Перезапустить
make restart
```

---

**Дата**: 15 октября 2025
**Статус**: Требуется исправление на сервере
