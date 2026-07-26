# PENT-F17 — чек-лист владельцу edge/обсервабилити

_Составлено 2026-07-26 по фактическому состоянию profk (все ответы ниже получены
запросами с самого хоста, а не из документации)._

Пункт был сформулирован узко: «health-роут есть в коде, но на проде
`/uk/api/health` → 404, мониторинг может не заметить отказ API». Разбор показал
**четыре разных ложно-зелёных состояния**, и три из них правятся только в файлах
владельца — они и есть содержание этого чек-листа. Наша часть уже сделана в
репозитории (см. последний раздел).

Главное, что стоит прочитать целиком: **ни одна публичная проба сегодня не
доказывает, что приложения живы.** `/health` на обоих доменах — константа
nginx'а; `/uk/health` отдавал SPA-страницу; проба «management-api жив» упирается
в 404 от edge и до апстрима не доходит. Единственный честный слой — внутренние
blackbox-пробы alloy, бьющие прямо в контейнеры. То есть при живом nginx и
мёртвом UK API снаружи всё зелёное, и это ровно тот сценарий, о котором пункт.

## Что измерено

| Проверка | Факт на 2026-07-26 |
|---|---|
| `https://profk.uz/health` | `200 text/plain` `healthy` — **строка, синтезированная самим nginx** (`location /health { return 200 "healthy\n"; }`, `nginx.profk.conf:649`). Ни одного приложения не касается: зелено, пока жив nginx. То же на `infrasafe.uz` (`nginx.production.conf:630`) |
| `https://profk.uz/uk/health` | `200 text/html`, SPA `index.html` — **было** ложно-зелёным (закрыто в репо) |
| `https://profk.uz/uk/api/health` | `404 text/html` от **самого nginx** — путь не в prefix-allowlist SEC-22 |
| `https://profk.uz/uk/api/v1/` | `404 text/html` от **nginx** — запрос до апстрима не доходит |
| `https://profk.uz/uk/api/v2/requests/__nope__` | `401 application/json` от FastAPI — этот путь до апстрима доходит |
| `https://profk.uz/uk/api/v1/access/health` | `404 application/json` от access-api — доходит (своя location) |
| blackbox-проба alloy | `http://uk-management-api:8080/health` — **честная**, единственный слой, который сегодня видит смерть UK API |

## Задача 1 (обязательная) — открыть `/uk/api/health` в allowlist

Файл: `/opt/infrasafe/nginx-config/nginx.profk.conf`, блок `map $uri $uk_api_allowed`
(там же, где остальные префиксы контракта УК). Добавить одну строку:

```nginx
        # PENT-F17: публичная liveness-проба UK API. Открыта сознательно:
        # отдаёт ровно {"ok":true}, без имени сервиса и версии (fingerprinting).
        # Ops-эндпоинты (/api/health/ratelimit, /api/health/outbox) остаются
        # закрытыми — они под HEALTH_METRICS_TOKEN и в allowlist не входят.
        "~^/uk/api/health$"                  1;
```

Точное совпадение (`$`), а не префикс — иначе под правило попали бы
`/uk/api/health/ratelimit` и `/uk/api/health/outbox`, которые закрыты намеренно.

Проверка после `nginx -t && nginx -s reload`:

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://profk.uz/uk/api/health
# ожидаем: 200 application/json
curl -s https://profk.uz/uk/api/health          # {"ok":true}
curl -s -o /dev/null -w '%{http_code}\n' https://profk.uz/uk/api/health/outbox
# ожидаем: 404 — ops-эндпоинт остался закрыт
```

## Задача 2 (обязательная) — починить ложно-зелёную пробу «management-api жив»

Файл: `/opt/profk-observability/uptime-kuma/provision.js`.

Монитор `"profk.uz — management-api жив"` смотрит на `https://profk.uz/uk/api/v1/`
с допуском `200-499` по логике «живой апстрим ответит 404, мёртвый даст 502».
Для access-api это верно (его путь внутри своей location и проксируется), **а для
management-api — нет**: `/uk/api/v1/` не входит в allowlist, поэтому `404`
возвращает сам edge, не касаясь апстрима. Монитор остаётся зелёным при полностью
мёртвом `uk-management-api`.

После задачи 1 заменить на честную проверку:

```js
    { ...HTTP_DEFAULTS, name: "profk.uz — management-api жив",
        url: "https://profk.uz/uk/api/health",
        description: "200 + {\"ok\":true} от FastAPI. 502/504 = api не поднят." },
```

Именно `HTTP_DEFAULTS` (200-299), а не `HTTP_UPSTREAM` (200-499): у этого пути
есть настоящий 200, и допускать 4xx больше не нужно — ровно допуск 4xx и делал
проверку нечувствительной к отказу.

⚠️ Для `infrasafe.uz` (хост .105) та же правка требует **сначала** задачи 1 в
конфиге того домена. До этого монитор `.105` оставить как есть, иначе он
покраснеет на 404 от edge.

Заодно стоит добавить цель в `external-probe/hosts/infrasafe105.probe.conf`
(`TARGETS=...`) — внешний слой сейчас проверяет `/`, `/uk/` и `/health`, то есть
про UK API не знает ничего.

## Задача 3 (обязательная) — `/health` на edge не должен выглядеть как health приложения

`location /health` в **обоих** конфигах (`nginx.profk.conf:649`,
`nginx.production.conf:630`) — это `return 200 "healthy\n"` самого nginx. Проба
доказывает единственное: nginx принимает соединения. При этом на неё опираются
сразу три места:

* blackbox-проба alloy `https://profk.uz/health` (`config.alloy:152`);
* peer-проба `https://infrasafe.uz/health` (`config.alloy:163`);
* мониторы Uptime Kuma «profk.uz — /health» и «infrasafe.uz — /health»
  (`provision.js`, у второго описание «Приложение на .105» — фактически неверное).

Варианты, любой из двух:

**(а) оставить как есть, но перестать называть это health приложения** —
переименовать мониторы в «edge (nginx) жив» и поправить описания. Дешево, честно,
ничего не ломает. Тогда роль «здоровье приложений» целиком остаётся на задачах
1–2 и внутренних пробах.

**(б) сделать `/health` проксируемым** на реальный апстрим того домена. Дороже:
`/health` на корне — исторически внешний контракт, и смена его поведения может
задеть чужие проверки, о которых мы не знаем.

Рекомендация — **(а)**: минимум риска, а правдивую проверку UK API даёт задача 1.

## Что уже сделано в репозитории (раскатывается обычным деплоем `frontend`)

* `frontend/nginx.conf` — `location = /health { return 404; }`. SPA больше не
  отвечает `200 text/html` на liveness-пробу. Проверено, что `/uk/health` не
  опрашивает ни один слой (alloy, Uptime Kuma, external-probe), и что у
  контейнера `uk-frontend` нет healthcheck'а — ломать нечего.
* `tests/api/test_health_contract.py` — контракт: `/api/health` → `200`,
  `application/json`, ровно `{"ok": true}`, без HTML-маркеров в теле; `/health`
  сохраняет тело `{"status":"healthy","service":"api"}` (на него бьёт
  blackbox-проба); и config-гейт на `frontend/nginx.conf`, чтобы SPA-fallback на
  `/health` не воскрес незаметно.

**Порядок:** наш деплой `frontend` можно катать независимо; задача 2 — только
после задачи 1. Негативную проверку (остановить `uk-management-api` и убедиться,
что монитор краснеет) на проде **не проводить** — только на локальном/стейдж-стенде.
