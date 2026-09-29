# Media-service

> _Последнее редактирование: 2026-09-29 (ревью медиасервиса 2026-09-28)_

Хранит фото/видео заявок, фотоотчётов, обратной связи и кадров проезда.
Байты лежат в приватных Telegram-каналах (свой бот `MEDIA_BOT_TOKEN`),
метаданные — в БД `uk_media` (роль `uk_media_owner`). Код — `media_service/`.
Деплой и секреты — `.claude/skills/uk-deploy/SKILL.md`.

## Доступ

- Внутри docker-сети: `http://media-service:8000`, заголовок `X-API-Key`
  (любой ключ из `MEDIA_API_KEYS`).
- На хосте (profk и 105): `127.0.0.1:8009`, снаружи порт не опубликован.
- Без ключа отвечают только `/api/v1/health`, `/api/v1/health/live`,
  `/api/v1/health/ready` (цель docker healthcheck: проверяет БД).
- Swagger (`/docs`) на проде выключен (`DEBUG=false`).

## Ручной поиск фото (VPN)

Эндпоинты поиска **не удалять**: владелец ищет по ним фото заявок вручную
(решение 2026-09-28). Вызовов из кода у них нет — это нормально.

```bash
# 1) туннель к хосту (VPN включён)
ssh -N -L 8009:127.0.0.1:8009 profk          # или infrasafe105

# 2) ключ — в переменную, не на экран
export KEY=$(doppler secrets get MEDIA_API_KEY --plain --project uk-management --config profk)
M=http://127.0.0.1:8009/api/v1/media

# все файлы заявки (метаданные; id — для скачивания)
curl -s -H "X-API-Key: $KEY" "$M/request/260926-001?limit=200" | jq '.[] | {id, category, uploaded_at}'
# хронология файлов заявки
curl -s -H "X-API-Key: $KEY" "$M/request/260926-001/timeline" | jq
# сам файл
curl -s -H "X-API-Key: $KEY" "$M/123/file" -o 123.jpg
# поиск: текст (регистр не важен, кириллица тоже), теги, даты, категории
curl -s -G -H "X-API-Key: $KEY" "$M/search" --data-urlencode "query=кран" \
     --data-urlencode "categories=completion_photo" --data-urlencode "date_from=2026-09-01T00:00:00" | jq
# по Telegram file_id: метаданные / байты (удалённые в БД файлы — 404)
curl -s -H "X-API-Key: $KEY" "$M/telegram/<file_id>" | jq
curl -s -H "X-API-Key: $KEY" "$M/telegram/<file_id>/file" -o file.jpg
# сводка и популярные теги
curl -s -H "X-API-Key: $KEY" "$M/statistics" | jq
curl -s -H "X-API-Key: $KEY" "$M/tags/popular" | jq
```

Параметры `/search`: `query`, `request_numbers`, `tags`, `file_types`,
`categories` (списки через запятую), `date_from`/`date_to` (ISO),
`telegram_file_id`, `uploaded_by` (внутренний `users.id`), `status`
(по умолчанию `active`), `limit` ≤ 200, `offset`.

## Эндпоинты и потребители

Префикс `/api/v1/media`.

| Эндпоинт | Кто вызывает |
|---|---|
| `POST /upload` | API-прокси (дашборд/TWA), обратная связь, бот (фото заявок, документы онбординга) |
| `POST /upload-report` | бот и API (фотоотчёт исполнителя) |
| `POST /upload-access` | access-api (кадры проезда) |
| `GET /{id}`, `GET /{id}/file` | API-прокси (с проверкой доступа к заявке), бот (байты), витрина, access-api |
| `GET /{id}/preview`, `POST /previews/warm` | публичная витрина работ |
| `GET /request/{n}` | API-прокси, бот (фотоотчёт, отчёты работ) |
| `DELETE /{id}` | бот (документы пользователя), access-api |
| `POST/DELETE /{id}/publication-lock`, `GET /publication-locks`, `POST /maintenance/resolve-stale-transitions` | отчёты работ (сага, reconcile) |
| `GET /maintenance/preview-cache` | вручную после деплоя |
| `GET /search`, `/statistics`, `/tags/popular`, `/request/{n}/timeline`, `/{id}/url`, `/telegram/{file_id}`, `/telegram/{file_id}/file` | **ручной поиск владельца** |
| `PUT /{id}/tags`, `POST /{id}/archive`, `GET /{id}/similar` | вызовов нет (решение по удалению — бэклог A9-P2-24) |

## Контракт с клиентами

- Ответ загрузки вложенный: `media_file.id`, а не `id`.
- `uploaded_by` — внутренний `users.id` (колонка INT4), не Telegram ID;
  `request_number` ≤ 20 символов. Нарушение — 422 до отправки в Telegram.
- Тип файла сервис выводит из байтов; заявленный `Content-Type` роли не играет.
- `telegram_file_id` выдан медиа-ботом — основной бот отправляет такие файлы
  байтами (`services/request_media_entries.send_media_entries`).
- 502 от `/{id}/file` значит «сервис уже ретраил скачивание у Telegram в своём
  бюджете 25 с» — клиенты его не повторяют (`FILE_RETRY_STATUSES`).
