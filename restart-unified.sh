#!/bin/bash
# Перезапуск сервисов

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "🔄 Перезапуск всех сервисов..."
    docker-compose -f docker-compose.unified.yml restart
    echo "✅ Все сервисы перезапущены"
else
    echo "🔄 Перезапуск сервиса: $SERVICE..."
    docker-compose -f docker-compose.unified.yml restart "$SERVICE"
    echo "✅ Сервис $SERVICE перезапущен"
fi

echo ""
echo "📊 Статус сервисов:"
docker-compose -f docker-compose.unified.yml ps
