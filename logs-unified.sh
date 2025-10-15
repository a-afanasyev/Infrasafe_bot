#!/bin/bash
# Просмотр логов всех сервисов

SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "📋 Логи всех сервисов (Ctrl+C для выхода):"
    docker-compose -f docker-compose.unified.yml logs -f
else
    echo "📋 Логи сервиса: $SERVICE (Ctrl+C для выхода):"
    docker-compose -f docker-compose.unified.yml logs -f "$SERVICE"
fi
