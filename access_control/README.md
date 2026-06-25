# Access Control

Будущий модуль контроля въезда, парковочного доступа и гостевых пропусков.

Архитектурное решение: отдельный доменный сервис внутри текущего монорепозитория. Он переиспользует пользователей, квартиры, auth и общую инфраструктуру, но расширяет ролевую модель значениями `system_admin` и `security_operator`. Автомобили, пропуска, ANPR-события, решения доступа и ручные открытия хранятся отдельно от текущих сервисных заявок УК.

Актуальное ТЗ версии 1.4: [docs/access-control/TECHNICAL_SPEC.md](../docs/access-control/TECHNICAL_SPEC.md). Первая реализация ограничена пилотным ядром на одной зоне.

Планируемая структура:

```text
app/            # сборка FastAPI-приложения модуля
api/            # HTTP/WebSocket endpoints
domain/         # модели домена, enum'ы, правила доступа
services/       # access decision engine и бизнес-сервисы
integrations/   # Hikvision, relay, Telegram, media adapters
edge/           # протоколы edge-контроллеров и offline sync
tests/          # unit/integration tests
```
