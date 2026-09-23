FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

WORKDIR /srv/app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

# AUD7-ENG-08: рантайм api/worker/migrate — не root. Код и зависимости
# ставятся root'ом в системный site-packages (только чтение), сервису на
# запись нужен лишь /tmp (heartbeat воркера); volumes у сервисов нет.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

COPY --chown=appuser:appuser . .
# AUD7-ENG-03: зависимости — из hash-locked requirements.txt (uv pip compile
# pyproject.toml, команда в шапке файла), сам пакет — --no-deps, чтобы
# pyproject не мог подтянуть ничего мимо lock.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

USER appuser

EXPOSE 8100
# A9-P3-26: ENTRYPOINT scripts/entrypoint-api.sh удалён — после AUD6-P1-2
# (миграции ушли в one-shot resource-migrate) в нём оставался только
# `exec "$@"`. CMD в exec-форме и так даёт uvicorn PID 1; resource-worker и
# resource-migrate задают свои entrypoint/command в compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
