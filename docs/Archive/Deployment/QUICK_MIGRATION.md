# ⚡ Быстрая миграция базы данных

> _Последнее редактирование: 2025-10-29_

**Самый простой способ перенести БД с локальной машины на сервер**

---

## 🚀 Один командой (автоматический скрипт)

```bash
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK
./scripts/migrate_database.sh user your-server-ip
```

**Замените**:
- `user` - ваш пользователь на сервере
- `your-server-ip` - IP адрес сервера (например: `192.168.1.100`)

**Пример**:
```bash
./scripts/migrate_database.sh user 178.20.155.123
```

---

## 📋 Что делает скрипт

1. ✅ Создает backup локальной БД
2. ✅ Останавливает локального бота
3. ✅ Копирует backup на сервер
4. ✅ Создает backup текущей БД на сервере
5. ✅ Пересоздает БД на сервере
6. ✅ Восстанавливает данные из backup
7. ✅ Проверяет количество записей
8. ✅ Запускает бота на сервере

**Время выполнения**: 2-5 минут (зависит от размера БД и скорости интернета)

---

## 📦 Что вам нужно

### На локальной машине:
- ✅ Docker запущен
- ✅ Локальная БД с данными
- ✅ SSH доступ к серверу

### На сервере:
- ✅ Docker контейнеры запущены
- ✅ SSH ключи настроены (для входа без пароля)

---

## 🔧 Пошаговая миграция вручную

Если автоматический скрипт не подходит:

### 1. На локальной машине

```bash
# Создать backup
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK
mkdir -p ~/backups
docker-compose -f docker-compose.dev.yml exec -T postgres pg_dump \
  -U uk_bot -d uk_management --clean --if-exists --no-owner --no-privileges \
  > ~/backups/uk_management_$(date +%Y%m%d_%H%M%S).sql

# Посмотреть размер
ls -lh ~/backups/

# Скопировать на сервер
scp ~/backups/uk_management_*.sql user@your-server-ip:~/
```

### 2. На сервере

```bash
# Подключиться к серверу
ssh user@your-server-ip
cd ~/Infrasafe_bot

# Остановить бота
docker stop uk-bot

# Пересоздать БД
docker exec uk-postgres psql -U uk_bot -d postgres -c "DROP DATABASE IF EXISTS uk_management;"
docker exec uk-postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;"

# Восстановить данные
cat ~/uk_management_*.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management

# Запустить бота
docker start uk-bot

# Проверить логи
docker logs -f uk-bot
```

---

## ✅ Проверка после миграции

```bash
# На сервере проверить количество записей
docker exec uk-postgres psql -U uk_bot -d uk_management -c "
SELECT 'users' as table, COUNT(*) FROM users
UNION ALL SELECT 'requests', COUNT(*) FROM requests
UNION ALL SELECT 'shifts', COUNT(*) FROM shifts;
"

# Проверить что бот запустился
docker logs uk-bot | grep "готов к работе"

# Проверить в Telegram что бот отвечает
```

---

## 🆘 Если что-то пошло не так

### Откат на сервере

```bash
# Восстановить из backup который создали ДО миграции
ssh user@your-server-ip
cd ~/Infrasafe_bot

docker stop uk-bot

docker exec uk-postgres psql -U uk_bot -d postgres -c "DROP DATABASE IF EXISTS uk_management;"
docker exec uk-postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;"

cat ~/backup_before_migration_*.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management

docker start uk-bot
```

### Проблемы с подключением к серверу

```bash
# Проверить SSH ключи
ssh user@your-server-ip

# Если не работает, сгенерировать новый ключ
ssh-keygen -t rsa -b 4096
ssh-copy-id user@your-server-ip
```

---

## 💡 Советы

1. **Время суток**: Делайте миграцию когда бот не активен (ночью или рано утром)
2. **Backup**: Всегда сохраняйте backup файлы минимум неделю
3. **Проверка**: После миграции проверьте все критические функции
4. **Уведомления**: Предупредите пользователей о возможном простое

---

## 📚 Подробная документация

Полное руководство с объяснениями: [`DATABASE_MIGRATION_GUIDE.md`](./DATABASE_MIGRATION_GUIDE.md)

---

**Создано**: 15 октября 2025
**Версия**: 1.0
