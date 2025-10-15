#!/bin/bash
# Скрипт остановки единого окружения

set -e

echo "🛑 Остановка UK Management Bot + Media Service..."

docker-compose -f docker-compose.unified.yml down

echo "✅ Все сервисы остановлены"
