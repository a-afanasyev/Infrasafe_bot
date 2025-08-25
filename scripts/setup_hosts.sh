#!/bin/bash

# Домен для тестирования
DOMAIN="uk-management.local"
HOSTS_ENTRY="127.0.0.1 $DOMAIN"

echo "🔧 Настройка hosts файла для тестирования..."

# Проверяем, есть ли уже запись в hosts
if grep -q "$DOMAIN" /etc/hosts; then
    echo "✅ Запись для $DOMAIN уже существует в /etc/hosts"
else
    echo "📝 Добавляем запись в /etc/hosts..."
    echo "$HOSTS_ENTRY" | sudo tee -a /etc/hosts
    echo "✅ Запись добавлена: $HOSTS_ENTRY"
fi

echo ""
echo "🌐 Теперь можно использовать домен: https://$DOMAIN"
echo "📋 Для проверки выполните: curl -k https://$DOMAIN"
