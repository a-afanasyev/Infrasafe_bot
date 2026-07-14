FROM python:3.12-slim

WORKDIR /srv/app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir .

RUN chmod +x scripts/entrypoint-api.sh

EXPOSE 8100
ENTRYPOINT ["/srv/app/scripts/entrypoint-api.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
