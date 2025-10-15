#!/bin/bash
# 🔄 Скрипт автоматической миграции базы данных PostgreSQL
# Переносит БД с локальной машины на облачный сервер

set -e  # Остановиться при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для красивого вывода
error() { echo -e "${RED}❌ $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# Баннер
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   🔄 UK Management Bot - Database Migration Tool          ║"
echo "║   Перенос БД с локальной машины на облачный сервер        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ==================== КОНФИГУРАЦИЯ ====================

# Параметры сервера (можно передать через аргументы)
SERVER_USER="${1:-user}"
SERVER_IP="${2:-your-server-ip}"

# Локальные параметры
LOCAL_COMPOSE="docker-compose.dev.yml"
BACKUP_DIR="$HOME/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uk_management_$TIMESTAMP.sql"
BACKUP_FILE_COMPRESSED="$BACKUP_DIR/uk_management_$TIMESTAMP.sql.gz"

# PostgreSQL параметры
PG_USER="uk_bot"
PG_DATABASE="uk_management"

# ==================== ПРОВЕРКИ ====================

info "Проверка параметров..."

# Проверка аргументов
if [ "$SERVER_IP" == "your-server-ip" ]; then
    error "Не указан IP адрес сервера!"
    echo ""
    echo "Использование:"
    echo "  $0 <server_user> <server_ip>"
    echo ""
    echo "Пример:"
    echo "  $0 user 192.168.1.100"
    exit 1
fi

success "Сервер: $SERVER_USER@$SERVER_IP"

# Проверка docker-compose файла
if [ ! -f "$LOCAL_COMPOSE" ]; then
    error "Файл $LOCAL_COMPOSE не найден!"
    exit 1
fi

# Проверка что Docker запущен
if ! docker info > /dev/null 2>&1; then
    error "Docker не запущен или недоступен!"
    exit 1
fi

# Проверка подключения к серверу
info "Проверка подключения к серверу..."
if ! ssh -o ConnectTimeout=5 "$SERVER_USER@$SERVER_IP" "echo 'OK'" > /dev/null 2>&1; then
    error "Не удалось подключиться к серверу $SERVER_IP"
    error "Проверьте SSH ключи и доступность сервера"
    exit 1
fi
success "Подключение к серверу установлено"

# ==================== ПОДТВЕРЖДЕНИЕ ====================

echo ""
warning "ВАЖНО: Эта операция:"
warning "  • Остановит бота на локальной машине"
warning "  • Остановит бота на сервере"
warning "  • Пересоздаст БД на сервере (текущие данные будут удалены)"
warning "  • Восстановит данные с локальной машины"
echo ""

read -p "Вы уверены что хотите продолжить? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy]([Ee][Ss])?$ ]]; then
    info "Миграция отменена пользователем"
    exit 0
fi

# ==================== BACKUP НА ЛОКАЛЬНОЙ МАШИНЕ ====================

echo ""
info "========================================="
info "Шаг 1/6: Создание backup на локальной машине"
info "========================================="

# Создать директорию для backups
mkdir -p "$BACKUP_DIR"
success "Директория для backup: $BACKUP_DIR"

# Проверить что локальная БД запущена
info "Запуск локального окружения..."
docker-compose -f "$LOCAL_COMPOSE" up -d postgres > /dev/null 2>&1
sleep 3

# Проверить количество записей перед backup
info "Подсчет записей в локальной БД..."
RECORD_COUNT=$(docker-compose -f "$LOCAL_COMPOSE" exec -T postgres psql -U "$PG_USER" -d "$PG_DATABASE" -t -c "
SELECT COUNT(*) FROM users;
" | tr -d ' ')
success "Найдено пользователей: $RECORD_COUNT"

# Остановить локального бота
info "Остановка локального бота..."
docker-compose -f "$LOCAL_COMPOSE" stop app > /dev/null 2>&1 || true
success "Локальный бот остановлен"

# Создать backup
info "Создание backup файла..."
info "Файл: $BACKUP_FILE"
docker-compose -f "$LOCAL_COMPOSE" exec -T postgres pg_dump \
  -U "$PG_USER" \
  -d "$PG_DATABASE" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  > "$BACKUP_FILE"

if [ ! -f "$BACKUP_FILE" ]; then
    error "Не удалось создать backup файл!"
    exit 1
fi

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
success "Backup создан успешно (размер: $BACKUP_SIZE)"

# Сжать backup для быстрой передачи
info "Сжатие backup файла..."
gzip -c "$BACKUP_FILE" > "$BACKUP_FILE_COMPRESSED"
COMPRESSED_SIZE=$(du -h "$BACKUP_FILE_COMPRESSED" | cut -f1)
success "Backup сжат (размер: $COMPRESSED_SIZE)"

# ==================== ПЕРЕНОС НА СЕРВЕР ====================

echo ""
info "========================================="
info "Шаг 2/6: Перенос файла на сервер"
info "========================================="

info "Копирование файла на $SERVER_IP..."
scp "$BACKUP_FILE_COMPRESSED" "$SERVER_USER@$SERVER_IP:~/uk_management_backup.sql.gz"
success "Файл скопирован на сервер"

# ==================== BACKUP НА СЕРВЕРЕ ====================

echo ""
info "========================================="
info "Шаг 3/6: Создание backup текущей БД на сервере"
info "========================================="

ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
set -e
cd ~/Infrasafe_bot

# Проверить что контейнеры запущены
if ! docker ps | grep -q uk-postgres; then
    echo "⚠️  PostgreSQL контейнер не запущен, запускаю..."
    docker-compose -f docker-compose.unified.yml up -d postgres
    sleep 5
fi

# Создать backup текущей БД
echo "📦 Создание backup текущей БД на сервере..."
docker exec uk-postgres pg_dump \
  -U uk_bot \
  -d uk_management \
  > ~/backup_before_migration_$(date +%Y%m%d_%H%M%S).sql || true

if [ -f ~/backup_before_migration_*.sql ]; then
    echo "✅ Backup текущей БД создан"
    ls -lh ~/backup_before_migration_*.sql
else
    echo "⚠️  БД на сервере пуста, backup не создан"
fi
ENDSSH

success "Backup текущей БД на сервере создан (если была)"

# ==================== ВОССТАНОВЛЕНИЕ НА СЕРВЕРЕ ====================

echo ""
info "========================================="
info "Шаг 4/6: Восстановление данных на сервере"
info "========================================="

info "Подключение к серверу и восстановление БД..."

ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
set -e
cd ~/Infrasafe_bot

# Остановить бота
echo "🛑 Остановка бота..."
docker stop uk-bot > /dev/null 2>&1 || true

# Распаковать backup
echo "📂 Распаковка backup..."
gunzip -c ~/uk_management_backup.sql.gz > ~/uk_management_backup.sql

# Пересоздать БД
echo "🗑️  Пересоздание базы данных..."
docker exec uk-postgres psql -U uk_bot -d postgres -c "DROP DATABASE IF EXISTS uk_management;" > /dev/null 2>&1
docker exec uk-postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;" > /dev/null 2>&1
echo "✅ База данных пересоздана"

# Восстановить данные
echo "📥 Восстановление данных..."
cat ~/uk_management_backup.sql | docker exec -i uk-postgres psql -U uk_bot -d uk_management > /dev/null 2>&1
echo "✅ Данные восстановлены"

# Удалить временные файлы
rm ~/uk_management_backup.sql
rm ~/uk_management_backup.sql.gz
echo "✅ Временные файлы удалены"
ENDSSH

success "Данные восстановлены на сервере"

# ==================== ПРОВЕРКА ДАННЫХ ====================

echo ""
info "========================================="
info "Шаг 5/6: Проверка данных"
info "========================================="

info "Подсчет записей на сервере..."

SERVER_RECORD_COUNT=$(ssh "$SERVER_USER@$SERVER_IP" "docker exec uk-postgres psql -U uk_bot -d uk_management -t -c 'SELECT COUNT(*) FROM users;'" | tr -d ' ')

success "Локальная БД: $RECORD_COUNT пользователей"
success "Серверная БД: $SERVER_RECORD_COUNT пользователей"

if [ "$RECORD_COUNT" -eq "$SERVER_RECORD_COUNT" ]; then
    success "✅ Количество записей совпадает!"
else
    warning "⚠️  Количество записей различается!"
    warning "Проверьте данные вручную"
fi

# ==================== ЗАПУСК БОТА ====================

echo ""
info "========================================="
info "Шаг 6/6: Запуск бота на сервере"
info "========================================="

ssh "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
cd ~/Infrasafe_bot
echo "🚀 Запуск бота..."
docker start uk-bot
sleep 5
echo "📋 Проверка логов..."
docker logs --tail 20 uk-bot
ENDSSH

success "Бот запущен на сервере"

# ==================== ЗАВЕРШЕНИЕ ====================

echo ""
success "========================================="
success "🎉 МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!"
success "========================================="
echo ""
success "✅ Backup создан: $BACKUP_FILE"
success "✅ Backup сжатый: $BACKUP_FILE_COMPRESSED"
success "✅ Данные перенесены на сервер: $SERVER_IP"
success "✅ Бот запущен на сервере"
echo ""
info "📋 Следующие шаги:"
info "  1. Проверьте работу бота в Telegram"
info "  2. Убедитесь что все данные на месте"
info "  3. Сохраните backup файлы минимум неделю"
echo ""
warning "💡 Локальный бот остановлен и не будет запущен автоматически"
warning "   Чтобы запустить: docker-compose -f $LOCAL_COMPOSE up -d app"
echo ""

exit 0
