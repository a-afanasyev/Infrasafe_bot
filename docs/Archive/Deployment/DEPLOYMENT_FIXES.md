# 🔧 Исправления для развертывания на сервере

> _Последнее редактирование: 2026-05-30_

**Дата**: 15 октября 2025
**Проблема**: Ошибки при запуске `make start` на сервере

---

## 🐛 Найденные проблемы

### 1. ⚠️ "The 'afe' variable is not set"

**Причина**:
Docker Compose неправильно интерпретировал вложенные переменные в DATABASE_URL:
```yaml
DATABASE_URL=${DATABASE_URL:-postgresql://uk_bot:${POSTGRES_PASSWORD:-uk_bot_password}@postgres:5432/uk_management}
```

Когда пароль содержит `Example@Pw$` (спецсимвол `$`), Docker пытается разобрать `$…` как отдельную переменную.

**Решение**:
Убрали вложенные переменные, теперь DATABASE_URL полностью берется из .env:
```yaml
DATABASE_URL=${DATABASE_URL}
```

### 2. ⚠️ "version attribute is obsolete"

**Причина**:
Атрибут `version: '3.8'` устарел в новых версиях Docker Compose.

**Решение**:
Удален атрибут `version` из всех docker-compose файлов:
- `docker-compose.unified.yml`
- `docker-compose.prod.unified.yml`
- `docker-compose.dev.yml`
- `docker-compose.prod.yml`

---

## ✅ Внесенные изменения

### Файлы изменены:

1. **docker-compose.unified.yml**
   - Убраны вложенные переменные `${POSTGRES_PASSWORD}` из DATABASE_URL
   - DATABASE_URL теперь полностью из .env
   - ✅ Синтаксис проверен

2. **docker-compose.prod.unified.yml**
   - Те же изменения для production
   - ✅ Синтаксис проверен

3. **docker-compose.dev.yml**
   - Удален атрибут `version: '3.8'`

4. **docker-compose.prod.yml**
   - Удален атрибут `version: '3.8'`

5. **.env.unified.example**
   - Добавлены комментарии о URL-encoding для паролей со спецсимволами
   - Обновлена документация DATABASE_URL
   - Добавлена переменная MEDIA_BOT_TOKEN для отдельного медиа-бота

6. **SERVER_SETUP_GUIDE.md** (новый файл)
   - Полное руководство по развертыванию на сервере
   - Решение проблем со спецсимволами в паролях
   - Checklist для первого запуска
   - Секция диагностики проблем

---

## 📋 Инструкции для сервера

### Правильная настройка .env файла:

**Вариант 1: Простой пароль (рекомендуется)**
```bash
# .env
POSTGRES_PASSWORD=MySecurePassword123
DATABASE_URL=postgresql://uk_bot:MySecurePassword123@postgres:5432/uk_management
```

**Вариант 2: Пароль со спецсимволами (требует URL-encoding)**
```bash
# Если пароль Example@Pw$, то:
POSTGRES_PASSWORD=Example@Pw$
DATABASE_URL=postgresql://uk_bot:Example%40Pw%24@postgres:5432/uk_management
```

URL-encoding таблица:
- `@` → `%40`
- `$` → `%24`
- `#` → `%23`
- `:` → `%3A`
- `/` → `%2F`

### Минимальный .env для запуска:

```bash
# Обязательные параметры
BOT_TOKEN=your_bot_token_from_botfather
MEDIA_BOT_TOKEN=your_media_bot_token_from_botfather
POSTGRES_PASSWORD=YourSecurePassword123
DATABASE_URL=postgresql://uk_bot:YourSecurePassword123@postgres:5432/uk_management

# Рекомендуемые параметры
POSTGRES_DB=uk_management
POSTGRES_USER=uk_bot
REDIS_URL=redis://redis:6379/0
MEDIA_REDIS_URL=redis://redis:6379/1
LOG_LEVEL=INFO
DEBUG=false
```

---

## 🧪 Проверка исправлений

### Локальная проверка синтаксиса:
```bash
docker-compose -f docker-compose.unified.yml config
```
✅ Проверено - синтаксис правильный

### На сервере после git pull:
```bash
cd ~/Infrasafe_bot
git pull
cp .env.unified.example .env
nano .env  # Настроить BOT_TOKEN и пароли
make start
```

### Проверка запуска:
```bash
# Все 5 контейнеров должны быть Running
docker ps

# Healthcheck должен проходить
curl http://localhost:8009/api/v1/health
```

---

## 🔒 Security Notes

1. **Никогда не коммитьте .env файлы** - они в .gitignore
2. **Измените пароли для production** - не используйте примеры
3. **Закройте порты БД в production** - закомментируйте `ports:` в docker-compose
4. **Используйте сильные пароли** - минимум 12 символов
5. **Предпочитайте простые пароли без спецсимволов** - меньше проблем с escaping

---

## 📞 Поддержка

Если проблемы остались:
1. Проверьте логи: `docker logs uk-postgres`, `docker logs uk-bot`
2. Проверьте .env: `cat .env | grep -v "^#" | grep -v "^$"`
3. Полная очистка: `make clean && make start`

Подробное руководство: **SERVER_SETUP_GUIDE.md**

---

**Статус**: ✅ Ready for deployment
**Тестирование**: ✅ Синтаксис проверен
**Документация**: ✅ SERVER_SETUP_GUIDE.md создан
