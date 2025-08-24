# 🚀 PRODUCTION DEPLOYMENT GUIDE

## 🛡️ КРИТИЧНЫЕ ИСПРАВЛЕНИЯ БЕЗОПАСНОСТИ

### ✅ ВЫПОЛНЕННЫЕ ИСПРАВЛЕНИЯ

1. **🔐 Устранен дефолтный пароль администратора**
   - Удален дефолтный пароль "12345"
   - Добавлена обязательная проверка в production
   - В dev режиме используется безопасный временный пароль

2. **🔑 Обязательная проверка INVITE_SECRET**
   - Токены инвайтов требуют обязательный секретный ключ в production
   - Защита от подделки приглашений

3. **⚡ Redis поддержка для rate limiting**
   - Добавлена поддержка Redis для горизонтального масштабирования
   - Fallback к in-memory rate limiting при недоступности Redis
   - Конфигурируется через `USE_REDIS_RATE_LIMIT=true`

4. **🏥 Health Check endpoint**
   - `/health` - базовая проверка состояния
   - `/health_detailed` - детальная информация (только для менеджеров)
   - `/ping` - быстрая проверка доступности

5. **📊 Структурированное логирование**
   - JSON логи для production
   - Фильтрация чувствительной информации
   - Контекстные логи с метаданными

## 🔧 ПЕРЕД РАЗВЕРТЫВАНИЕМ

### 1. Обновление зависимостей

```bash
pip install -r requirements.txt
```

**Новые зависимости:**
- `redis>=5.0.0` - Redis клиент
- `aioredis>=2.0.1` - Async Redis
- `structlog>=23.1.0` - Структурированное логирование

### 2. Конфигурация окружения

Скопируйте `production.env.example` в `.env.production`:

```bash
cp uk_management_bot/production.env.example .env.production
```

**Обязательно измените:**

```bash
# Генерация безопасных паролей
openssl rand -base64 32  # для ADMIN_PASSWORD
openssl rand -base64 64  # для INVITE_SECRET
```

### 3. Проверка конфигурации

```bash
cd uk_management_bot
python -c "from config.settings import settings; print('✅ Configuration is valid')"
```

## 🐳 DOCKER РАЗВЕРТЫВАНИЕ

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY uk_management_bot/ ./uk_management_bot/

# Создание пользователя без прав root
RUN useradd -m -u 1000 ukbot && chown -R ukbot:ukbot /app
USER ukbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Запуск приложения
CMD ["python", "-m", "uk_management_bot.main"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  uk-bot:
    build: .
    container_name: uk-management-bot
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
    env_file:
      - .env.production
    environment:
      - DATABASE_URL=postgresql://ukbot:${DB_PASSWORD}@postgres:5432/uk_management
      - REDIS_URL=redis://redis:6379/0
      - USE_REDIS_RATE_LIMIT=true
    volumes:
      - ./logs:/app/logs
    networks:
      - uk-network
    healthcheck:
      test: ["CMD", "python", "-c", "from handlers.health import get_health_status; import asyncio; print(asyncio.run(get_health_status()))"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: postgres:15-alpine
    container_name: uk-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=ukbot
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=uk_management
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - uk-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ukbot"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    container_name: uk-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - uk-network
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
  redis_data:

networks:
  uk-network:
    driver: bridge
```

## 🔍 МОНИТОРИНГ

### Health Check Endpoints

1. **Базовый health check:**
   ```bash
   curl -X GET http://localhost:8080/health
   ```

2. **Детальная проверка (требует прав менеджера):**
   - Команда в Telegram: `/health_detailed`

3. **Быстрая проверка:**
   ```bash
   curl -X GET http://localhost:8080/ping
   ```

### Логирование

В production логи выводятся в JSON формате:

```json
{
  "timestamp": "2023-12-07T10:30:00.000Z",
  "level": "INFO",
  "logger": "uk_bot.auth",
  "message": "User login successful",
  "user_id": 123,
  "action": "login",
  "component": "auth"
}
```

**Фильтрация чувствительной информации:**
- Пароли, токены, секреты автоматически заменяются на `[REDACTED]`

## ⚙️ СИСТЕМНЫЕ ТРЕБОВАНИЯ

### Минимальные требования

- **CPU:** 1 vCPU
- **RAM:** 1GB
- **Disk:** 10GB
- **OS:** Ubuntu 20.04+ / CentOS 8+ / Alpine Linux

### Рекомендуемые требования

- **CPU:** 2 vCPU
- **RAM:** 4GB
- **Disk:** 20GB SSD
- **Network:** 100 Mbps

### Для высокой нагрузки (1000+ пользователей)

- **CPU:** 4+ vCPU
- **RAM:** 8GB
- **Disk:** 50GB SSD
- **Redis:** Отдельный сервер/кластер
- **PostgreSQL:** Отдельный сервер с репликацией

## 🔒 БЕЗОПАСНОСТЬ

### Обязательные меры

1. **Firewall настройки:**
   ```bash
   # Разрешить только необходимые порты
   ufw allow 22    # SSH
   ufw allow 80    # HTTP (если используется reverse proxy)
   ufw allow 443   # HTTPS (если используется reverse proxy)
   ufw enable
   ```

2. **SSL/TLS:**
   - Используйте Let's Encrypt для HTTPS
   - Настройте reverse proxy (Nginx/Apache)

3. **Backup стратегия:**
   ```bash
   # Ежедневный backup PostgreSQL
   pg_dump uk_management > backup_$(date +%Y%m%d).sql
   
   # Backup Redis (если критично)
   redis-cli BGSAVE
   ```

4. **Мониторинг логов:**
   ```bash
   # Мониторинг подозрительной активности
   tail -f /var/log/uk-bot/security.log | grep "SECURITY"
   ```

## 🚨 TROUBLESHOOTING

### Проблемы с подключением к Redis

```bash
# Проверка Redis
redis-cli ping

# Логи Redis
docker logs uk-redis
```

### Проблемы с базой данных

```bash
# Проверка PostgreSQL
pg_isready -h localhost -p 5432

# Логи PostgreSQL
docker logs uk-postgres
```

### Проблемы с ботом

```bash
# Проверка health
curl http://localhost:8080/health

# Логи бота
docker logs uk-management-bot
```

## 📞 ПОДДЕРЖКА

При проблемах с развертыванием:

1. Проверьте health check endpoints
2. Изучите логи в JSON формате
3. Убедитесь что все обязательные ENV переменные установлены
4. Проверьте сетевую доступность Redis и PostgreSQL

---

**⚠️ ВАЖНО:** После развертывания обязательно протестируйте все критичные функции:
- Создание заявок
- Система инвайтов
- Переключение ролей
- Health check endpoints
