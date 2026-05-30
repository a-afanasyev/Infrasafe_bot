# Dockerfile для UK Management Bot
# Используем официальный Python образ версии 3.11
# slim версия для уменьшения размера образа
FROM python:3.11-slim

# Устанавливаем метаданные образа
LABEL maintainer="UK Management Bot Team"
LABEL description="Telegram бот для управляющей компании"
LABEL version="1.0.0"

# Устанавливаем рабочую директорию в контейнере
# Это директория, где будет находиться код приложения
WORKDIR /app

# Устанавливаем системные зависимости
# Эти пакеты необходимы для работы Python и некоторых библиотек
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
# Сначала копируем requirements.txt для оптимизации кэширования Docker слоев
COPY requirements.txt .
COPY uk_management_bot/requirements.txt ./uk_management_bot/
COPY requirements-dev.txt .

# OPS-117 — dev-deps по умолчанию включены: образ используется для тестов
# (`docker exec uk-management-bot pytest` per CLAUDE.md), а tests/ всё равно
# копируются в этот же image (см. COPY tests/ ниже). Чистый prod-build:
# `docker compose build --build-arg INSTALL_DEV=false app`.
ARG INSTALL_DEV=true

# Устанавливаем Python зависимости
# --no-cache-dir уменьшает размер образа
# --upgrade обновляет пакеты до последних версий
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r uk_management_bot/requirements.txt && \
    if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    fi

# Копируем весь код приложения
# Копируем папку uk_management_bot в контейнер
COPY uk_management_bot/ ./uk_management_bot/

# Копируем тесты
COPY tests/ ./tests/

# pytest-конфиг (testpaths, asyncio_mode, import-mode) — без него
# `docker exec uk-management-bot pytest` игнорирует config и собирает не тот скоуп
COPY pyproject.toml ./

# Создаем пользователя для безопасности
# Запуск приложения от имени непривилегированного пользователя
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Копируем entrypoint скрипт
COPY scripts/entrypoint-bot.sh /app/entrypoint.sh
USER root
RUN chmod +x /app/entrypoint.sh

# Переключаемся на пользователя app
USER app

ENTRYPOINT ["/app/entrypoint.sh"]

# Устанавливаем переменные окружения по умолчанию
# Эти переменные можно переопределить при запуске контейнера
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Открываем порт для health checks
# Бот работает через Telegram API, но порт нужен для проверки состояния
EXPOSE 8000

# Создаем health check
# Проверяем доступность приложения каждые 30 секунд
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Команда запуска приложения
# Запускаем бота через Python модуль
CMD ["python", "uk_management_bot/main.py"]
