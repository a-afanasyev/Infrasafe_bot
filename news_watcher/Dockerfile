# Юзербот мониторинга отключений — отдельный образ: Telethon в основной образ
# бота/API не тянем (hash-lock requirements.txt, другой процесс, другой риск).
FROM python:3.11-slim@sha256:cdbd05fb6f457ca275ff51ce00d93d865ca0b6a25f5ffb08262d94f6835771e5
WORKDIR /app
ENV PIP_RETRIES=10 PIP_DEFAULT_TIMEOUT=60 PYTHONUNBUFFERED=1
# requirements.txt — hash-lock (uv pip compile requirements.in --generate-hashes),
# гейт uk_management_bot/tests/test_ci_service_coverage.py.
COPY news_watcher/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY news_watcher/ ./news_watcher/
RUN useradd -r -u 10001 watcher && mkdir -p /data && chown watcher /data
USER watcher
VOLUME ["/data"]
CMD ["python", "-m", "news_watcher.main"]
