#!/bin/bash
# Скрипт запуска единого окружения (бот + медиа-сервис)

set -e

echo "🚀 Запуск UK Management Bot + Media Service..."

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Создайте .env файл на основе .env.example"
    exit 1
fi

# Проверка наличия BOT_TOKEN
if ! grep -q "^BOT_TOKEN=" .env || [ -z "$(grep "^BOT_TOKEN=" .env | cut -d '=' -f2)" ]; then
    echo "❌ BOT_TOKEN не установлен в .env файле!"
    exit 1
fi

# Создание директорий для медиа
mkdir -p media_service/data/uploads
echo "✅ Директории для медиа созданы"

# Создание channels.json если не существует
if [ ! -f media_service/channels.json ]; then
    echo '{
  "channels": [],
  "version": "1.0"
}' > media_service/channels.json
    echo "✅ Создан файл channels.json"
fi

# Остановка старых контейнеров
echo "🛑 Остановка старых контейнеров..."
docker-compose -f docker-compose.unified.yml down

# Запуск всех сервисов
echo "🔄 Запуск сервисов..."
docker-compose -f docker-compose.unified.yml up -d

# Ожидание запуска
echo "⏳ Ожидание запуска сервисов (30 секунд)..."
sleep 30

# Проверка статуса
echo ""
echo "📊 Статус сервисов:"
docker-compose -f docker-compose.unified.yml ps

echo ""
echo "✅ Запуск завершен!"
echo ""
echo "🔗 Доступные сервисы:"
echo "  • Telegram Bot: запущен"
echo "  • Media Service API: http://localhost:8009"
echo "  • Media Frontend: http://localhost:8010"
echo "  • PostgreSQL: localhost:5432"
echo "  • Redis: localhost:6379"
echo ""
echo "📝 Полезные команды:"
echo "  • Логи всех сервисов: docker-compose -f docker-compose.unified.yml logs -f"
echo "  • Логи бота: docker-compose -f docker-compose.unified.yml logs -f bot"
echo "  • Логи медиа: docker-compose -f docker-compose.unified.yml logs -f media-service"
echo "  • Остановка: docker-compose -f docker-compose.unified.yml down"
echo "  • Перезапуск: docker-compose -f docker-compose.unified.yml restart"
echo ""
