#!/bin/bash
# Скрипт тестирования Media Service

set -e

API_URL="http://localhost:8009/api/v1"

echo "🧪 Тестирование Media Service..."
echo ""

# 1. Health Check
echo "1️⃣ Проверка здоровья сервиса..."
HEALTH=$(curl -s ${API_URL}/health)
echo "   Ответ: $HEALTH"
if echo "$HEALTH" | grep -q "healthy"; then
    echo "   ✅ Сервис работает"
else
    echo "   ❌ Сервис недоступен"
    exit 1
fi
echo ""

# 2. Список каналов
echo "2️⃣ Получение списка каналов..."
CHANNELS=$(curl -s ${API_URL}/channels)
echo "   Найдено каналов: $(echo $CHANNELS | jq '. | length')"
echo "   Каналы:"
echo "$CHANNELS" | jq -r '.[] | "     - \(.id): \(.name) (\(.enabled))"'
echo ""

# 3. Статистика кеша
echo "3️⃣ Статистика кеша..."
STATS=$(curl -s ${API_URL}/cache/stats)
echo "$STATS" | jq '.'
echo ""

# 4. Тест загрузки (если есть тестовый файл)
if [ -f "test_image.jpg" ]; then
    echo "4️⃣ Тест загрузки файла..."
    UPLOAD_RESULT=$(curl -s -X POST "${API_URL}/media/upload" \
        -F "file=@test_image.jpg" \
        -F "channel_id=photos")
    echo "   Результат:"
    echo "$UPLOAD_RESULT" | jq '.'

    # Извлекаем file_id для следующих тестов
    FILE_ID=$(echo "$UPLOAD_RESULT" | jq -r '.file_id')

    if [ "$FILE_ID" != "null" ] && [ -n "$FILE_ID" ]; then
        echo "   ✅ Файл загружен: $FILE_ID"

        # 5. Получение информации о файле
        echo ""
        echo "5️⃣ Получение информации о файле..."
        FILE_INFO=$(curl -s "${API_URL}/media/${FILE_ID}")
        echo "$FILE_INFO" | jq '.'

        # 6. Получение URL для скачивания
        echo ""
        echo "6️⃣ Получение URL для скачивания..."
        DOWNLOAD_URL=$(curl -s "${API_URL}/media/${FILE_ID}/url")
        echo "   URL: $(echo $DOWNLOAD_URL | jq -r '.url')"
        echo "   Срок действия: $(echo $DOWNLOAD_URL | jq -r '.expires_at')"
    else
        echo "   ❌ Ошибка загрузки файла"
    fi
else
    echo "4️⃣ Пропущен (нет тестового файла test_image.jpg)"
fi

echo ""
echo "✅ Тестирование завершено!"
echo ""
echo "📊 Для просмотра метрик откройте:"
echo "   http://localhost:8009/metrics"
echo ""
echo "🌐 Для веб-интерфейса откройте:"
echo "   http://localhost:8010"
echo ""
