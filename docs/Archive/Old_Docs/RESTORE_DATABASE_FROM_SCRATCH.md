# 🔧 Восстановление БД с нуля после удаления контейнеров

> _Последнее редактирование: 2025-10-29_

**Ситуация**: Случайно удалили Docker контейнеры с базой данных на сервере
**Решение**: Восстановить из backup с локальной машины

---

## 🎯 Быстрое решение (3 шага)

### На локальной машине:

```bash
# Шаг 1: Создать backup локальной БД
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK
make export-db

# Результат: создан файл backups/export_20251015_HHMMSS.sql
```

### Перенести на сервер:

```bash
# Шаг 2: Скопировать backup на сервер
scp backups/export_*.sql user@your-server-ip:~/
```

### На сервере:

```bash
# Шаг 3: Импортировать БД
cd ~/Infrasafe_bot
make init                              # Если не делали
make import-db FILE=~/export_*.sql     # Восстановить БД
make start                             # Запустить всё
```

---

## 📋 Детальная инструкция

### Часть 1: Экспорт БД на локальной машине

```bash
# 1. Перейти в директорию проекта
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK

# 2. Убедиться что локальная БД запущена
docker-compose -f docker-compose.dev.yml up -d postgres

# 3. Проверить данные
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management -c "
SELECT 'users' as table, COUNT(*) as count FROM users
UNION ALL SELECT 'requests', COUNT(*) FROM requests
UNION ALL SELECT 'shifts', COUNT(*) FROM shifts
UNION ALL SELECT 'addresses', COUNT(*) FROM addresses;
"

# 4. Создать backup
mkdir -p backups
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  > backups/local_backup_$(date +%Y%m%d_%H%M%S).sql

# 5. Проверить размер файла
ls -lh backups/local_backup_*.sql
```

**Результат**: У вас есть файл `backups/local_backup_YYYYMMDD_HHMMSS.sql`

---

### Часть 2: Перенос на сервер

```bash
# Найти последний backup
BACKUP_FILE=$(ls -t backups/local_backup_*.sql | head -1)
echo "Переносим: $BACKUP_FILE"

# Скопировать на сервер (замените user и IP)
scp "$BACKUP_FILE" user@192.168.1.100:~/database_backup.sql

# Проверить что файл скопирован
ssh user@192.168.1.100 "ls -lh ~/database_backup.sql"
```

---

### Часть 3: Восстановление на сервере

```bash
# 1. Подключиться к серверу
ssh user@192.168.1.100

# 2. Перейти в директорию проекта
cd ~/Infrasafe_bot

# 3. Проверить что репозиторий обновлен
git pull

# 4. Инициализировать проект (если еще не делали)
make init

# 5. Настроить .env файл
nano .env
# Установить:
# - BOT_TOKEN=ваш_токен
# - MEDIA_BOT_TOKEN=ваш_медиа_токен
# - POSTGRES_PASSWORD=YourPassword123
# - DATABASE_URL=postgresql://uk_bot:YourPassword123@postgres:5432/uk_management

# 6. Запустить PostgreSQL
make start

# Дождаться пока PostgreSQL запустится (10-15 секунд)
docker logs uk-postgres

# 7. Импортировать БД
make import-db FILE=~/database_backup.sql

# 8. Проверить данные
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT 'users' as table, COUNT(*) as count FROM users
UNION ALL SELECT 'requests', COUNT(*) FROM requests
UNION ALL SELECT 'shifts', COUNT(*) FROM shifts;
"

# 9. Запустить всё
make restart

# 10. Проверить логи
make logs-bot
```

---

## ✅ Проверка успешного восстановления

```bash
# На сервере:

# 1. Проверить что все контейнеры запущены
docker ps
# Должны быть: uk-bot, uk-postgres, uk-redis, uk-media-service, uk-media-frontend

# 2. Проверить логи бота
docker logs uk-bot | grep "готов к работе"

# 3. Проверить количество записей
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT COUNT(*) FROM users;
"

# 4. Проверить что бот отвечает в Telegram
# Отправьте /start боту
```

---

## 🔄 Автоматическая миграция (альтернатива)

Если хотите всё одной командой с локальной машины:

```bash
# На локальной машине:
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK
./scripts/migrate_database.sh user 192.168.1.100
```

Этот скрипт автоматически:
- Создаст backup локальной БД
- Скопирует на сервер
- Восстановит на сервере
- Запустит бота

---

## ⚠️ Важные замечания

### 1. Если БД на сервере уже существует

```bash
# Скрипт автоматически создает backup перед импортом
# Backup сохраняется в: ~/backup_before_import_YYYYMMDD_HHMMSS.sql
```

### 2. Если нужно откатить импорт

```bash
# На сервере:
make import-db FILE=~/backup_before_import_*.sql
```

### 3. Если возникают ошибки

```bash
# Проверить что PostgreSQL запущен
docker ps | grep postgres

# Проверить логи PostgreSQL
docker logs uk-postgres

# Проверить что файл существует
ls -lh ~/database_backup.sql

# Проверить формат файла (первые строки)
head -20 ~/database_backup.sql
```

---

## 📊 Сравнение методов

| Метод | Время | Сложность | Контроль |
|-------|-------|-----------|----------|
| **Автоматический скрипт** | 2-3 мин | Низкая | Средний |
| **make export + import** | 5-7 мин | Средняя | Высокий |
| **Ручной backup/restore** | 10-15 мин | Высокая | Полный |

**Рекомендация**: Используйте `make export-db` + `make import-db` для максимального контроля

---

## 🎯 Checklist восстановления

**На локальной машине**:
- [ ] Локальная БД запущена
- [ ] Backup создан (`make export-db`)
- [ ] Размер файла проверен
- [ ] Файл скопирован на сервер

**На сервере**:
- [ ] Репозиторий обновлен (`git pull`)
- [ ] Инициализация выполнена (`make init`)
- [ ] .env файл настроен
- [ ] PostgreSQL запущен
- [ ] БД импортирована (`make import-db`)
- [ ] Количество записей проверено
- [ ] Бот запущен
- [ ] Бот отвечает в Telegram

---

## 🆘 Помощь

### Проблема: "Database does not exist"

```bash
# Создать БД вручную
docker exec uk-postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;"
```

### Проблема: "Permission denied"

```bash
# Прове��ить права на файл
chmod 644 ~/database_backup.sql

# Проверить владельца
ls -l ~/database_backup.sql
```

### Проблема: "Connection refused"

```bash
# Проверить что PostgreSQL запущен
docker ps | grep postgres

# Перезапустить PostgreSQL
docker restart uk-postgres

# Подождать 10 секунд и попробовать снова
```

---

## 📞 Дополнительная информация

- Полное руководство: `DATABASE_MIGRATION_GUIDE.md`
- Быстрая миграция: `QUICK_MIGRATION.md`
- Автоматический скрипт: `scripts/migrate_database.sh`

---

**Создано**: 15 октября 2025
**Версия**: 1.0
**Статус**: Tested and ready
