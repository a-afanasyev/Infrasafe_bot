# 🔄 Руководство по миграции базы данных на облачный сервер

**Цель**: Перенести базу данных PostgreSQL с локального окружения разработки на облачный сервер

---

## 📋 Содержание

1. [Подготовка к миграции](#подготовка)
2. [Создание backup на локальной машине](#backup)
3. [Перенос файла на сервер](#transfer)
4. [Восстановление на сервере](#restore)
5. [Проверка данных](#verification)
6. [Откат при необходимости](#rollback)

---

## 🎯 Подготовка к миграции {#подготовка}

### 1. Проверка локальной БД

На **локальной машине**:

```bash
# Запустить локальное окружение
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK
docker-compose -f docker-compose.dev.yml up -d

# Проверить что БД работает
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management -c "\dt"

# Посмотреть количество записей
docker-compose -f docker-compose.dev.yml exec postgres psql -U uk_bot -d uk_management -c "
SELECT
    'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'requests', COUNT(*) FROM requests
UNION ALL
SELECT 'shifts', COUNT(*) FROM shifts
UNION ALL
SELECT 'addresses', COUNT(*) FROM addresses;
"
```

### 2. Остановить бота на локальной машине

```bash
# Остановить бота, чтобы не было изменений во время backup
docker-compose -f docker-compose.dev.yml stop app
```

---

## 💾 Создание backup на локальной машине {#backup}

### Способ 1: Полный backup с pg_dump (Рекомендуется)

```bash
# Создать директорию для backups
mkdir -p ~/backups

# Создать backup всей БД
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  > ~/backups/uk_management_$(date +%Y%m%d_%H%M%S).sql

# Проверить размер файла
ls -lh ~/backups/uk_management_*.sql

# Посмотреть первые строки для проверки
head -n 50 ~/backups/uk_management_*.sql
```

**Опции pg_dump**:
- `--clean` - добавляет DROP TABLE перед CREATE TABLE
- `--if-exists` - использует IF EXISTS для DROP
- `--no-owner` - не восстанавливает владельцев объектов
- `--no-privileges` - не восстанавливает права доступа

### Способ 2: Backup с сжатием (для больших БД)

```bash
# Создать сжатый backup
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  | gzip > ~/backups/uk_management_$(date +%Y%m%d_%H%M%S).sql.gz

# Проверить размер
ls -lh ~/backups/uk_management_*.sql.gz
```

### Способ 3: Только данные (без схемы)

Если схема уже создана на сервере через Alembic:

```bash
# Только данные
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --data-only \
  --column-inserts \
  > ~/backups/uk_management_data_$(date +%Y%m%d_%H%M%S).sql
```

---

## 📤 Перенос файла на сервер {#transfer}

### Способ 1: SCP (безопасная копия)

```bash
# Узнать имя последнего backup файла
BACKUP_FILE=$(ls -t ~/backups/uk_management_*.sql | head -1)
echo "Переносим файл: $BACKUP_FILE"

# Скопировать на сервер
scp "$BACKUP_FILE" user@your-server-ip:~/

# Или если используется сжатый файл
BACKUP_FILE=$(ls -t ~/backups/uk_management_*.sql.gz | head -1)
scp "$BACKUP_FILE" user@your-server-ip:~/
```

### Способ 2: Прямая передача через SSH

```bash
# Создать backup и сразу передать на сервер
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  | ssh user@your-server-ip "cat > ~/uk_management_backup.sql"
```

### Способ 3: Через промежуточное хранилище

```bash
# Загрузить на облачное хранилище (Dropbox, Google Drive и т.д.)
# Затем скачать на сервере
```

---

## 📥 Восстановление на сервере {#restore}

### Подключитесь к серверу

```bash
ssh user@your-server-ip
cd ~/Infrasafe_bot
```

### 1. Остановить бота на сервере

```bash
# Остановить только бота, оставить БД работать
docker stop uk-bot
```

### 2. Создать backup текущей БД на сервере (на всякий случай)

```bash
# Создать backup перед восстановлением
docker exec uk-postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  > ~/backup_before_migration_$(date +%Y%m%d_%H%M%S).sql

echo "✅ Backup текущей БД создан"
```

### 3. Очистить текущую БД

**Вариант A: Пересоздать БД полностью (рекомендуется)**

```bash
# Подключиться к PostgreSQL
docker exec -it uk-postgres psql -U uk_bot -d postgres

# В psql выполнить:
DROP DATABASE IF EXISTS uk_management;
CREATE DATABASE uk_management OWNER uk_bot;
\q

echo "✅ База данных пересоздана"
```

**Вариант B: Удалить все таблицы (если хотите сохранить БД)**

```bash
docker exec -it uk-postgres psql -U uk_bot -d uk_management -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO uk_bot;
"
```

### 4. Восстановить данные из backup

**Если файл несжатый (.sql)**:

```bash
# Найти файл backup
ls -lh ~/*.sql

# Восстановить из backup
cat ~/uk_management_*.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management

echo "✅ Данные восстановлены"
```

**Если файл сжатый (.sql.gz)**:

```bash
# Распаковать и восстановить
gunzip -c ~/uk_management_*.sql.gz | docker exec -i uk-postgres psql -U uk_bot -d uk_management
```

### 5. Применить миграции Alembic (если нужно)

```bash
# Если схема БД отличается, применить миграции
docker exec uk-bot alembic upgrade head
```

---

## ✅ Проверка данных {#verification}

### 1. Проверить количество записей

```bash
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT
    'users' as table_name, COUNT(*) as count FROM users
UNION ALL
SELECT 'requests', COUNT(*) FROM requests
UNION ALL
SELECT 'shifts', COUNT(*) FROM shifts
UNION ALL
SELECT 'addresses', COUNT(*) FROM addresses
UNION ALL
SELECT 'audit_logs', COUNT(*) FROM audit_logs;
"
```

**Сравните с данными локальной БД!**

### 2. Проверить п��следние записи

```bash
# Последние пользователи
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT id, telegram_id, username, created_at
FROM users
ORDER BY created_at DESC
LIMIT 5;
"

# Последние заявки
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT request_number, title, status, created_at
FROM requests
ORDER BY created_at DESC
LIMIT 5;
"
```

### 3. Проверить целостность данных

```bash
# Проверить foreign keys
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name,
    confrelid::regclass AS referenced_table
FROM pg_constraint
WHERE contype = 'f';
"
```

### 4. Запустить бота и проверить работу

```bash
# Запустить бота
docker start uk-bot

# Следить за логами
docker logs -f uk-bot

# Проверить что бот запустился без ошибок
docker logs uk-bot | grep -i "готов к работе"
```

---

## 🔄 Откат при необходимости {#rollback}

Если что-то пошло не так:

```bash
# 1. Остановить бота
docker stop uk-bot

# 2. Пересоздать БД
docker exec -it uk-postgres psql -U uk_bot -d postgres -c "
DROP DATABASE IF EXISTS uk_management;
CREATE DATABASE uk_management OWNER uk_bot;
"

# 3. Восстановить из backup который создали ДО миграции
cat ~/backup_before_migration_*.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management

# 4. Запустить бота
docker start uk-bot
```

---

## 📝 Чеклист миграции

### Подготовка
- [ ] Проверена локальная БД
- [ ] Локальный бот остановлен
- [ ] Создан backup на локальной машине
- [ ] Backup файл проверен (размер, содержимое)

### Перенос
- [ ] Файл скопирован на сервер
- [ ] Размер файла на сервере совпадает с оригиналом

### Восстановление на сервере
- [ ] Бот остановлен
- [ ] Создан backup текущей БД
- [ ] БД очищена
- [ ] Данные восстановлены из backup
- [ ] Миграции Alembic применены (если нужно)

### Проверка
- [ ] Количество записей совпадает
- [ ] Последние записи на месте
- [ ] Foreign keys целы
- [ ] Бот запущен без ошибок
- [ ] Бот отвечает в Telegram

### Завершение
- [ ] Старый backup файл удален (или сохранен в архив)
- [ ] Локальный бот можно запускать снова

---

## ⚙️ Автоматический скрипт миграции

Создайте файл `migrate_db.sh` для автоматизации:

```bash
#!/bin/bash
set -e

echo "🔄 Начало миграции базы данных"

# Параметры
SERVER_USER="user"
SERVER_IP="your-server-ip"
LOCAL_COMPOSE="docker-compose.dev.yml"
BACKUP_DIR="$HOME/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uk_management_$TIMESTAMP.sql"

# 1. Создать backup на локальной машине
echo "📦 Создание backup локальной БД..."
mkdir -p "$BACKUP_DIR"
docker-compose -f "$LOCAL_COMPOSE" exec -T postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  > "$BACKUP_FILE"

echo "✅ Backup создан: $BACKUP_FILE"
echo "📊 Размер: $(du -h "$BACKUP_FILE" | cut -f1)"

# 2. Скопировать на сервер
echo "📤 Копирование на сервер..."
scp "$BACKUP_FILE" "$SERVER_USER@$SERVER_IP:~/uk_management_backup.sql"

# 3. Восстановить на сервере
echo "📥 Восстановление на сервере..."
ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
cd ~/Infrasafe_bot

# Остановить бота
docker stop uk-bot

# Создать backup текущей БД
docker exec uk-postgres pg_dump -U uk_bot -d uk_management > ~/backup_before_migration.sql

# Пересоздать БД
docker exec uk-postgres psql -U uk_bot -d postgres -c "DROP DATABASE IF EXISTS uk_management;"
docker exec uk-postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;"

# Восстановить данные
cat ~/uk_management_backup.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management

# Запустить бота
docker start uk-bot

# Удалить временный файл
rm ~/uk_management_backup.sql

echo "✅ Миграция завершена на сервере"
ENDSSH

echo "🎉 Миграция успешно завершена!"
echo "📋 Backup сохранен: $BACKUP_FILE"
```

**Использование**:
```bash
chmod +x migrate_db.sh
./migrate_db.sh
```

---

## 🚨 Важные замечания

1. **Всегда создавайте backup** перед миграцией
2. **Остановите ботов** на обеих сторонах во время переноса
3. **Проверяйте данные** после восстановления
4. **Сохраняйте backup файлы** минимум неделю после миграции
5. **Используйте одинаковые версии PostgreSQL** на обеих сторонах
6. **Проверьте права доступа** к файлам backup

---

## 📞 Помощь при проблемах

### Ошибка: "permission denied"
```bash
# Проверить владельца файла
ls -l ~/uk_management_backup.sql

# Изменить права
chmod 644 ~/uk_management_backup.sql
```

### Ошибка: "database is being accessed by other users"
```bash
# Отключить все подключения
docker exec uk-postgres psql -U uk_bot -d postgres -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'uk_management' AND pid <> pg_backend_pid();
"
```

### Ошибка: "out of memory"
```bash
# Увеличить лимит памяти для Docker
# В Docker Desktop: Settings → Resources → Memory

# Или восстановить частями (для очень больших БД)
```

---

**Создано**: 15 октября 2025
**Версия**: 1.0
**Статус**: Ready for production
