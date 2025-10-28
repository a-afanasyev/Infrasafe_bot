# Быстрый Старт: Единое Окружение

Запуск UK Management Bot + Media Service одной командой.

---

## ⚡ За 3 минуты

### 1. Настройка (первый раз)

```bash
# Создайте .env файл
cp .env.example .env

# Добавьте BOT_TOKEN
echo "BOT_TOKEN=your_telegram_bot_token" >> .env
```

### 2. Запуск

```bash
# Запустить всё
./start-unified.sh
```

Подождите 30 секунд... Готово! 🎉

---

## 🌐 Проверка

| Что проверить | Как |
|---------------|-----|
| **Бот запущен** | Напишите боту в Telegram |
| **Media API** | http://localhost:8009/api/v1/health |
| **Web Interface** | http://localhost:8010 |
| **Database** | `docker-compose -f docker-compose.unified.yml exec postgres pg_isready` |

---

## 📋 Основные команды

```bash
# Логи
./logs-unified.sh              # Все логи
./logs-unified.sh bot          # Только бот
./logs-unified.sh media-service # Только медиа

# Перезапуск
./restart-unified.sh           # Все сервисы
./restart-unified.sh bot       # Только бот

# Остановка
./stop-unified.sh

# Тестирование Media Service
./test-media-service.sh
```

---

## 🧪 Быстрый тест

```bash
# 1. Проверка здоровья
curl http://localhost:8009/api/v1/health

# 2. Список каналов
curl http://localhost:8009/api/v1/channels | jq

# 3. Загрузка файла
curl -X POST "http://localhost:8009/api/v1/media/upload" \
  -F "file=@photo.jpg" \
  -F "channel_id=photos"

# Или откройте веб-интерфейс
open http://localhost:8010
```

---

## 🔍 Что-то не работает?

### Бот не отвечает
```bash
# Проверьте логи
./logs-unified.sh bot | tail -50

# Перезапустите
./restart-unified.sh bot
```

### Media Service недоступен
```bash
# Проверьте статус
docker-compose -f docker-compose.unified.yml ps media-service

# Проверьте логи
./logs-unified.sh media-service
```

### База данных не подключается
```bash
# Проверьте PostgreSQL
docker-compose -f docker-compose.unified.yml exec postgres pg_isready

# Пересоздайте контейнер
docker-compose -f docker-compose.unified.yml up -d --force-recreate postgres
```

### Порт занят
```bash
# Найдите процесс
lsof -i :8009
lsof -i :5432

# Остановите старые контейнеры
docker ps
docker stop <container_id>
```

---

## 📚 Полная документация

Подробные инструкции: [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md)

---

## 🎯 Архитектура

```
┌──────────────┐      ┌──────────────┐
│ Telegram Bot │◄────►│ Media Service│
│  (Python)    │      │   (FastAPI)  │
└──────┬───────┘      └──────┬───────┘
       │                     │
       └─────────┬───────────┘
                 ▼
        ┌────────────────┐
        │   PostgreSQL   │
        └────────────────┘
                 ▲
                 │
        ┌────────────────┐
        │     Redis      │
        └────────────────┘
```

---

## 💾 Данные

Все данные сохраняются в Docker volumes:
- `postgres_data` - База данных
- `redis_data` - Кеш Redis
- `media_uploads` - Загруженные файлы

**Backup базы:**
```bash
docker-compose -f docker-compose.unified.yml exec postgres \
  pg_dump -U uk_bot uk_management > backup.sql
```

---

## 🚀 Production Deployment

Для production используйте:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

Отличия от dev:
- ✅ Оптимизированные образы
- ✅ Без volume mapping
- ✅ Production настройки безопасности
- ✅ Rate limiting
- ✅ Log rotation

---

**Версия**: 1.0.0
**Обновлено**: 15.10.2025
**Поддержка**: См. [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md)
