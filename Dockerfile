# Dockerfile для UK Management Bot
# Используем официальный Python образ версии 3.11
# slim версия для уменьшения размера образа
# Base запинен по digest (tag: python:3.11-slim) — стабильный cache-key pip-слоя,
# чтобы ре-таг базы наверху не инвалидировал его и не гонял pip по сети заново.
# Обновлять digest осознанно при апгрейде базы.
FROM python:3.11-slim@sha256:cdbd05fb6f457ca275ff51ce00d93d865ca0b6a25f5ffb08262d94f6835771e5

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

# PIP_RETRIES / PIP_DEFAULT_TIMEOUT — устойчивость к транзиентным флапам PyPI CDN
# (деплой 2026-06-25: ReadTimeout / "from versions: none" на здоровой сети
# посреди установки). Дефолты (5 ретраев / 15с) были слишком жёсткими.
ENV PIP_RETRIES=10 \
    PIP_DEFAULT_TIMEOUT=60

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

# Контроль доступа (ТЗ §6.4): общий доменный слой access_control должен быть в
# bot-образе — раздел жителя зовёт access_control.services.resident.* в процессе на
# общей БД (как в Dockerfile.api). Зависимости лёгкие (sqlalchemy + domain-модели,
# без fastapi) — в том же общем repo.
COPY access_control ./access_control

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Команда запуска приложения
# Запускаем бота через Python модуль
CMD ["python", "uk_management_bot/main.py"]
