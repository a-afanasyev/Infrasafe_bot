#!/bin/bash

# Создаем директорию для SSL сертификатов
mkdir -p ssl

# Создаем конфигурационный файл для OpenSSL
cat > ssl/openssl.conf << EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = RU
ST = Moscow
L = Moscow
O = UK Management
OU = Development
CN = uk-management.local

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = uk-management.local
DNS.3 = *.uk-management.local
EOF

# Генерируем самоподписанный сертификат с поддержкой нескольких доменов
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes -config ssl/openssl.conf -extensions v3_req

echo "✅ SSL сертификаты созданы в директории ssl/"
echo "📁 cert.pem - публичный сертификат"
echo "📁 key.pem - приватный ключ"
