# Аудит безопасности и пентест profk.uz

Дата: 11 июля 2026 года  
Объект: `profk.uz`, приложение `/uk`, основной FastAPI API, Access API, WebSocket, React frontend, production Docker-конфигурация  
Формат: статический аудит исходного кода + dependency audit + неразрушающий black-box пентест  
Авторизация: владелец домена подтвердил право на тестирование; публичная WHOIS-запись проверена  

## 1. Резюме

Критических удалённо эксплуатируемых уязвимостей без авторизации не обнаружено.
Выявлены три проблемы высокого приоритета, шесть среднего приоритета и ряд
замечаний по усилению защиты.

| Критичность | Количество | Основные риски |
|---|---:|---|
| Critical | 0 | Не обнаружено |
| High | 3 | DB superuser, refresh-token race, неверные slash-redirects auth API |
| Medium | 6 | WebSocket authorization/DoS, уязвимый aiohttp, CSV injection, frontend headers, DNS/TLS почты |
| Low | 7 | Права `.env`, proxy trust, Host header, DNS hardening, security.txt, banners, конфликтующие headers |
| Informational | 2 | Неработающий health-route, неприменимый advisory ecdsa |

Главные действия перед расширением production-нагрузки:

1. Устранить `307`-редиректы, теряющие HTTPS и `/uk`.
2. Отделить миграционную роль PostgreSQL от runtime-ролей приложений.
3. Сделать ротацию refresh-token атомарной и добавить replay detection.
4. Ограничить неаутентифицированный WebSocket handshake по времени.
5. Исправить security headers frontend и обновить `aiohttp`.

## 2. Границы и методика

Проверялись:

- FastAPI authentication, JWT, refresh-token, Telegram Widget/TWA и MFA;
- RBAC и объектная авторизация заявок, медиа и Access API;
- WebSocket authentication и жизненный цикл соединений;
- загрузка и выдача файлов, MIME validation, IDOR и path traversal;
- webhook HMAC, replay protection и rate limiting;
- React/Vite frontend, потенциальные XSS sinks, хранение токенов и CSP;
- Docker/Compose, права контейнеров, сети и PostgreSQL roles;
- известные уязвимости Python и npm production dependencies;
- DNS, TLS, сертификат, доступные порты и HTTP-конфигурация `profk.uz`;
- CORS, методы HTTP, чувствительные пути, Host/proxy headers и URL normalization;
- безопасные отрицательные auth/JWT/injection-пробы.

Не выполнялись:

- DoS, flood, slowloris и массовый brute-force;
- социальная инженерия;
- изменение или удаление production-данных;
- эксплуатация с реальными пользовательскими credential;
- authenticated IDOR/RBAC black-box тесты без выделенных тестовых аккаунтов.

## 3. Находки высокого приоритета

### F-01 — приложения используют PostgreSQL superuser

Критичность: **High**  
Класс: excessive privileges / нарушение least privilege

Bot, основной API и Access API используют один `POSTGRES_USER`. Официальный
образ PostgreSQL создаёт этого пользователя как владельца/суперпользователя,
и тот же credential используется для runtime-запросов и запуска Alembic.

Доказательства:

- `docker-compose.profk.yml:32` — bot `DATABASE_URL`;
- `docker-compose.profk.yml:62` — API `DATABASE_URL`;
- `docker-compose.profk.yml:99` — Access API `DATABASE_URL`;
- `docker-compose.profk.yml:127-130` — создание PostgreSQL user;
- `scripts/init_postgres.sql:2-10` — операции от superuser;
- `scripts/entrypoint-api.sh:3-5` — миграции запускаются при старте API.

Риск: компрометация любого приложения даёт полный контроль над схемой и всеми
данными, включая возможность изменять аудит, создавать роли и выполнять DDL.

Рекомендации:

- создать отдельную роль `uk_migration_owner` для Alembic;
- создать непривилегированные runtime-роли для bot/API/access-api;
- выдавать только необходимые DML/sequence permissions;
- запускать миграции отдельной deploy-задачей;
- не передавать migration credential runtime-контейнерам.

### F-02 — параллельное повторное использование refresh-token

Критичность: **High**  
Класс: session management / credential replay

`POST /api/v2/auth/refresh` читает токен обычным `SELECT`, затем изменяет
`revoked_at` и создаёт новый токен. Блокировка строки или атомарный conditional
update отсутствуют. Два параллельных запроса могут оба увидеть старый токен
действительным и выпустить две независимые новые сессии.

Доказательство: `uk_management_bot/api/auth/router.py:279-300`.

Рекомендации:

- использовать `UPDATE ... WHERE revoked_at IS NULL ... RETURNING` либо
  `SELECT ... FOR UPDATE`;
- хранить token family / parent token;
- при повторном использовании уже ротированного токена отзывать всю family;
- добавить конкурентный PostgreSQL regression test.

### F-03 — auth slash-redirect теряет HTTPS и префикс `/uk`

Критичность: **High**  
Класс: reverse-proxy misconfiguration / credential routing

Production воспроизводит системный redirect:

```text
POST https://profk.uz/uk/api/v2/auth/login/
307 Location: http://profk.uz/api/v2/auth/login
```

Аналогично ведут себя `/refresh/`, `/profile/` и другие маршруты с лишним `/`.
Теряется внешний префикс `/uk`, а схема меняется на `http`.

Современный браузер после получения HSTS на API-ответе обновляет HTTP обратно
до HTTPS, но POST попадает в другой сервис на `/api/...`. Проверка с фиктивными
данными завершилась в корневом InfraSafe API с ответом `Access token is missing`.
Клиенты без HSTS могут повторить тело по открытому HTTP.

Риск: пароль, refresh-token или другое POST-тело может получить неправильный
сервис; для клиентов без HSTS возможен plaintext downgrade.

Рекомендации:

- nginx: передавать `X-Forwarded-Proto $scheme` и корректный host;
- Uvicorn: доверять proxy headers только от nginx IP/CIDR;
- настроить ASGI/Uvicorn `root_path=/uk`;
- отключить автоматический `redirect_slashes` для auth API либо объявить точные
  варианты маршрутов без downgrade redirect;
- regression test: trailing slash должен давать 404 либо HTTPS Location с `/uk`.

Связанный код запуска: `Dockerfile.api` — команда Uvicorn без root-path и
явного trusted proxy configuration.

## 4. Находки среднего приоритета

### F-04 — WebSocket доверяет устаревшим JWT roles

Критичность: **Medium**  
Класс: broken access control

Основной WebSocket и Access security feed проверяют роли только из JWT при
handshake. Статус пользователя и актуальные роли из БД не читаются. После
блокировки или удаления manager/security role существующее соединение остаётся
открытым; истечение `exp` после handshake также не закрывает поток.

Доказательства:

- `uk_management_bot/api/ws/router.py:71-107`;
- `access_control/api/ws_security.py:19-21`;
- `access_control/api/ws_security.py:96-118`.

Рекомендации:

- при handshake загружать пользователя и роли из БД;
- закрывать соединение в момент JWT `exp`;
- периодически перепроверять блокировку/роли либо использовать revocation events;
- удалить поддержку JWT в query string в основном WS.

### F-05 — Access WebSocket бесконечно ждёт первый auth-message

Критичность: **Medium**  
Класс: unauthenticated resource exhaustion

Black-box проверка показала: `wss://profk.uz/uk/ws/v1/access/security`
принимает handshake без токена и остаётся OPEN спустя 12 секунд. В коде
`await websocket.receive_json()` не ограничен timeout.

Доказательство: `access_control/api/ws_security.py:105-115`.

Риск: множество неаутентифицированных idle-соединений может занять worker
connections и память.

Рекомендации:

- `asyncio.wait_for(receive_json(), timeout=5..10)`;
- проверять `Origin` до `accept()`;
- nginx `limit_conn`/`limit_req` для WS handshake;
- ограничить максимальное число unauthenticated connections на IP.

### F-06 — известные уязвимости aiohttp 3.13.5

Критичность: **Medium**  
Класс: vulnerable dependency

`pip-audit` обнаружил advisories для `aiohttp==3.13.5`, включая проблемы TLS
connection reuse, cookies/redirects, multipart CRLF injection, HTTP parser,
WebSocket memory limits и resource exhaustion.

Доказательство: `requirements.txt:15`.

Часть server-side advisories неприменима к текущему использованию aiohttp через
aiogram, однако client-side проблемы и наличие пакета в production требуют
обновления.

Рекомендация: обновить до `aiohttp>=3.14.1`, пересобрать lockfile с hashes,
запустить оба набора backend tests и rebuild bot/API images.

### F-07 — CSV/Excel formula injection

Критичность: **Medium**  
Класс: stored spreadsheet injection

Экспорт операций и закупок пишет управляемые значения напрямую через
`csv.writer`. Значения, начинающиеся с `=`, `+`, `-`, `@`, tab или CR/LF,
могут интерпретироваться Excel/LibreOffice как формулы.

Доказательства:

- `uk_management_bot/api/materials/router.py:239-255`;
- `uk_management_bot/api/materials/router.py:291-297`.

Рекомендация: централизованная функция `escape_csv_cell`, префиксующая опасные
строки апострофом; добавить tests для supplier, reason, material name и unit.

### F-08 — security headers отсутствуют на UK HTML/JS

Критичность: **Medium**  
Класс: clickjacking / transport hardening

На production `/uk/`, `/uk/login` и статическом JS отсутствуют:

- `Strict-Transport-Security`;
- `X-Frame-Options`;
- `X-Content-Type-Options`;
- `Referrer-Policy`;
- `Permissions-Policy`.

CSP присутствует, но не содержит `frame-ancestors`. Домен не находится в HSTS
preload list.

Корневая причина: `location /assets/` и `location = /index.html` определяют
собственные `add_header`, поэтому nginx перестаёт наследовать server-level
HSTS и `nosniff`.

Доказательство: `frontend/nginx.conf:6-20`.

Рекомендации:

- подключать единый security-header snippet в каждом `location`;
- использовать `always`;
- добавить `frame-ancestors 'self'` либо `'none'`;
- проверить headers отдельно для HTML, JS/CSS и API.

### F-09 — некорректные www/MX и отсутствие anti-spoofing DNS

Критичность: **Medium**  
Класс: domain/email security misconfiguration

- `www.profk.uz` — CNAME на `profk.uz`, но сертификат содержит только SAN
  `profk.uz`; HTTPS завершается certificate name mismatch.
- MX равен `0 profk.uz`, однако SMTP-порты 25/465/587 недоступны.
- SPF и DMARC отсутствуют.

Риск: пользователи `www` получают TLS warning; почта не доставляется; домен легче
использовать для email spoofing.

Рекомендации:

- добавить `www.profk.uz` в сертификат и настроить HTTPS redirect либо удалить CNAME;
- если почта не используется: null MX `0 .`, SPF `v=spf1 -all`, DMARC `p=reject`;
- если используется: настроить MX провайдера, SPF, DKIM и DMARC.

## 5. Находки низкого приоритета

### F-10 — локальные `.env` доступны другим пользователям ОС

Критичность: **Low**

Проверенные `.env` имеют режим `0644` и содержат реальные токены/секреты.
Файлы корректно исключены из Git и Docker build context, но читаются другими
локальными пользователями.

Рекомендация: `chmod 600` для всех secret env files; проверить permissions на
production host; по возможности использовать secret manager.

### F-11 — rate limiter доверяет X-Real-IP от любого peer при пустом allowlist

Критичность: **Low**

Если `RATE_LIMIT_TRUSTED_PROXIES` пуст, `client_ip_key` доверяет `X-Real-IP`
без проверки TCP peer. Внешний nginx корректно перезаписывает header — black-box
обход не удался. Но другой контейнер в общей `uk-network`, способный обратиться
к API напрямую, сможет менять bucket.

Доказательство: `uk_management_bot/api/rate_limit_keys.py:51-55`.

Рекомендация: задать trusted proxy allowlist и не публиковать API в общие сети
без необходимости.

### F-12 — virtual host принимает произвольный Host

Критичность: **Low**

Запрос с TLS SNI `profk.uz` и `Host: evil.example` получил страницу profk.uz.
Redirect root при этом использует фиксированный `profk.uz`, прямого Host-header
poisoning не подтверждено.

Рекомендация: отдельный `default_server`, возвращающий 421/444; рабочий vhost
должен принимать только `profk.uz` и явно настроенный `www.profk.uz`.

### F-13 — отсутствуют DNSSEC, CAA и OCSP stapling

Критичность: **Low**

- DS/DNSSEC для `profk.uz` не обнаружен;
- CAA отсутствует;
- TLS-сервер не отправляет stapled OCSP response.

Рекомендации: включить DNSSEC у регистратора/DNS provider, добавить CAA для
выбранного CA, включить OCSP stapling при поддержке edge nginx.

### F-14 — отсутствует security.txt

Критичность: **Low**

`/.well-known/security.txt` и `/security.txt` возвращают HTML SPA с HTTP 200.
Это затрудняет ответственное сообщение об уязвимостях и создаёт false-positive
status для автоматических проверок.

Рекомендация: разместить RFC 9116 security.txt с contact, preferred languages,
policy и expiration; неизвестные служебные файлы должны возвращать 404.

### F-15 — раскрытие версии nginx по HTTP

Критичность: **Low**

Port 80 возвращает `Server: nginx/1.31.2`; HTTPS скрывает точную версию.

Рекомендация: `server_tokens off` на всех server blocks.

### F-16 — дублирующиеся и конфликтующие security headers API

Критичность: **Low**

API-ответы содержат два HSTS и одновременно `X-Frame-Options: DENY` и
`X-Frame-Options: SAMEORIGIN`. Современный CSP `frame-ancestors 'self'`
снижает риск, но итоговая политика неоднозначна для старых клиентов.

Рекомендация: назначить edge единственным владельцем headers либо удалять
upstream headers перед установкой канонического набора.

## 6. Информационные замечания

### F-17 — production health path не соответствует документации

`https://profk.uz/uk/api/health` и `/uk/api/health/ratelimit` возвращают 404,
хотя код и deployment comments считают `/uk/api/health` публичным health endpoint.

Риск преимущественно операционный: monitoring может не обнаружить отказ API.

### F-18 — advisory python-ecdsa сейчас неприменим

`pip-audit` сообщил timing advisory для `ecdsa==0.19.2` без fix version.
Текущие JWT используют HS256, а не P-256 ECDSA, поэтому эксплуатируемый путь
в приложении не обнаружен. Следует следить за dependency chain `python-jose` и
не включать ECDSA signing без смены библиотеки/оценки риска.

## 7. Подтверждённые защитные меры

- Снаружи доступны только TCP 80 и 443.
- 22, 3000, 5432, 6379, 8000, 8080, 8085, 8087 и 8443 не отвечают.
- TLS 1.0/1.1 отключены; TLS 1.2/1.3 работают.
- TLS 1.3 negotiated cipher: `TLS_AES_256_GCM_SHA384`.
- Сертификат `profk.uz` валиден и выдан Let's Encrypt.
- HTTP перенаправляется на HTTPS.
- TRACE запрещён; неподдерживаемые методы возвращают 405.
- Evil CORS origin отклонён без `Access-Control-Allow-Origin`.
- `.env`, `.git/HEAD`, `package.json`, Swagger и OpenAPI не раскрываются.
- Source maps production bundle не опубликованы.
- Production JS не содержит Telegram token, JWT literals, AWS keys, private keys
  или имён серверных secrets.
- Login SQL/NoSQL-подобные payloads не дали обхода.
- JWT `alg:none` отклонён.
- Невалидные Telegram Widget/TWA подписи отклонены.
- Unsigned webhook отклонён с 401.
- Login rate limit срабатывает после 10 попыток; spoofed `X-Real-IP` его не обошёл.
- Kanban, employees, addresses, materials, access registry и edge endpoints без
  авторизации возвращают 401.
- Публичный board API содержит агрегаты и не раскрывает request number, address,
  description или user/executor identifiers.
- File upload proxy проверяет magic bytes, размер и объектный доступ.
- REST RBAC повторно читает текущие роли пользователя из БД.
- Cookies в коде настроены `HttpOnly`, `Secure` в production и `SameSite=Strict`.
- API documentation отключается при `DEBUG=false`.
- Docker bot/API запускаются от непривилегированных пользователей.

## 8. Результаты автоматизированных проверок

| Проверка | Результат |
|---|---|
| Backend security/auth/access tests, набор 1 | 104 passed |
| Backend API/auth/webhook/media tests, набор 2 | 104 passed |
| Frontend Vitest | 324 passed |
| npm audit, production dependencies | 0 vulnerabilities |
| pip-audit | advisories в aiohttp и ecdsa; применимость описана выше |
| Secret scan tracked files | реальных secrets не найдено |
| Frontend source maps | не опубликованы |

## 9. Ограничения результата

Без временных production test accounts не выполнены black-box проверки:

- horizontal IDOR между двумя applicant;
- executor access только к назначенным заявкам;
- manager/system_admin privilege boundaries;
- фактические `Set-Cookie` после успешного входа;
- CSRF на authenticated mutations;
- refresh-token concurrency и family replay в production;
- upload/download файлов разных владельцев;
- отзыв роли/блокировка во время живого WebSocket;
- Access API zone scoping с реальными сущностями.

Для второй фазы нужны отдельные временные аккаунты applicant A, applicant B,
executor и manager, а также разрешение создавать и удалять только специально
помеченные тестовые заявки.

## 10. План исправлений

### В течение 24 часов

1. Исправить slash-redirect/proxy/root-path (`F-03`).
2. Добавить timeout и connection limits Access WebSocket (`F-05`).
3. Восстановить HSTS/nosniff/frame protection для HTML и assets (`F-08`).
4. Исправить сертификат `www` либо удалить DNS alias (`F-09`).
5. Ограничить права `.env` до `0600` (`F-10`).

### В течение недели

1. Разделить PostgreSQL migration/runtime roles (`F-01`).
2. Сделать refresh rotation атомарной и добавить replay detection (`F-02`).
3. Реализовать live revalidation/expiry для WebSocket (`F-04`).
4. Обновить `aiohttp` до 3.14.1+ (`F-06`).
5. Экранировать CSV export (`F-07`).
6. Настроить mail DNS/SPF/DMARC (`F-09`).
7. Установить trusted proxy allowlist (`F-11`).

### Плановый hardening

1. Закрыть неизвестные Host headers (`F-12`).
2. Включить DNSSEC/CAA/OCSP stapling (`F-13`).
3. Добавить security.txt (`F-14`).
4. Скрыть server version и унифицировать headers (`F-15`, `F-16`).
5. Исправить production health routing и monitoring (`F-17`).

## 11. Критерии повторной проверки

- trailing-slash auth URL даёт 404 либо HTTPS redirect с сохранённым `/uk`;
- два параллельных refresh-запроса: ровно один успешен, второй отзывает family;
- runtime DB role не может выполнять DDL, создавать роли и читать чужие схемы;
- unauthenticated Access WS закрывается максимум через 10 секунд;
- заблокированный пользователь теряет WS-доступ без ожидания ручного reconnect;
- HTML, JS и API имеют единый набор security headers;
- CSV-ячейки с `= + - @ tab CR LF` не исполняются как формулы;
- `https://www.profk.uz` имеет валидный сертификат либо не существует;
- SPF/DMARC/MX соответствуют фактическому использованию почты;
- оба backend test suites, frontend tests, npm audit и pip-audit проходят после rebuild.

