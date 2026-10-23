# Манифест бэклога

> Генерируется: `python3 scripts/backlog_manifest.py --write`.
> Руками не править — правки вносить в `ASSIGNMENT` в скрипте.

## Зачем

Агрегаты бэклога расходились с реальностью двумя способами: метод счёта не был зафиксирован, и часть пунктов закрывалась кодом без закрытия документом. Здесь метод счёта — код скрипта, а распределение по пакетам проверяется инвариантом: `--check` падает, если у открытого пункта нет пакета. Ровно так был потерян `PENT-F14` — группа писалась сокращением.

## Метод счёта

- **Пункт** = заголовок `##`…`####`, в теле которого есть `**Priority:**`.
  Заголовки-разделы без Priority пунктами не являются по определению.
- **Закрыт** = заголовок зачёркнут (`~~`) **или** содержит `✅`/`❌`.
  Второе условие обязательно: часть пунктов закрыта словом без зачёркивания,
  и без этого закрытое считалось бы открытым.
- **Агрегаты считаются из этой таблицы**, а не пересказом.

## Агрегаты

- пунктов всего (с Priority): **614**
- закрыто маркером: **575**
- открыто маркером: **39**

  - `actionable` — **19**
  - `decision` — **6**
  - `no-pr` — **1**
  - `deferred` — **13**

Из них actionable по приоритету: P2=2, P3=17.

Значения `status`:

| status | смысл |
|---|---|
| `actionable` | работа в коде/конфиге, пакет обязателен |
| `decision` | ждёт решения владельца; до решения кодовой работы нет |
| `calendar` | работа определена, ждёт календарного срока |
| `no-pr` | работа вне PR (локальные файлы, потенциально деструктивно) |
| `deferred` | решение принято — «не делать сейчас»; трекер, работы не ждём (в отличие от `decision`, где решения ещё нет) |
| `doc-closed` | по коду закрыт, открыт только в документе |

Значения `method` — **чем** установлен статус. `doc-<дата>` означает: взято
из code-verified записи бэклога той даты, **не** перепроверено сейчас.
`plan-2026-07-26` — перепроверено при составлении плана. `to-verify` —
статус ещё не установлен чтением кода, это первый шаг работы над пунктом.

## Таблица

| ID | P | status | method | Пакет | PR | Сервисы | Прод-верификация | Примечание |
|---|---|---|---|---|---|---|---|---|
| `AUD3-07` | P2 | deferred | verified-2026-09-15 | A2 | — | — | — | ратчет построен 2026-09-01: test_aud307_unconverted_ratchet, baseline 23 файла / 232 сайта, двунаправленный; срез 2026-09-15: 62 CONVERTED; конверсия «при касании», deferred-трекер класса |
| `AUD5-CODE-10` | P3 | deferred | verified-2026-09-15 | A5 | — | — | — | ратчет построен 2026-09-01: test_aud5_code10_long_functions_ratchet, baseline 40 файлов / 49 функций; срез 2026-09-15: 48 функций (комментарий гейта ещё 49); раскрой «при касании» под принуждением гейта |
| `AUD5-ARCH-4` | P2 | deferred | gate-2026-08-09 | A7 | — | — | — | гейт границы стоит (test_aud5_arch4_domain_boundary_gate); развязка (L) — только при намерении разносить сервисы |
| `A10-FE-01` | P2 | actionable | found-2026-10-23 | AUD10-CODE | — | frontend | — | telegram-web-app.js на всех страницах — грузить только для TWA/регистрации |
| `A10-FE-03` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | api, frontend | — | public/board-config отдаёт анониму операционные поля — PublicBoardConfigOut |
| `A10-FE-05` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | frontend | — | ветка TV-табло: t.me-ссылка через botHandle() (pre-merge) |
| `A10-INF-03` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | compose | — | cap_drop/read_only/pids_limit для прикладных контейнеров (no-new-privileges уже в A10-CODE-01) |
| `A10-INF-08` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | compose, redis | — | пароль Redis в argv (--requirepass, redis-cli -a) — конфиг-файл + REDISCLI_AUTH |
| `A10-INT-10` | P3 | decision | found-2026-10-24 | AUD10-CODE | — | api | — | elevators.read открывает заявки лифта с ФИО и смену статуса лифта исполнителю — сузить до elevators.manage или фильтр по назначению |
| `A10-INT-11` | P3 | decision | found-2026-10-24 | AUD10-CODE | — | api | — | POST /feedback без approved_only — действие feedback.create |
| `A10-INT-12` | P3 | decision | found-2026-10-24 | AUD10-CODE | — | api | — | request_photo доступен соседу по приёмке — причина доступа owner/executor/manager |
| `A10-INT-13` | P3 | actionable | found-2026-10-24 | AUD10-CODE | — | bot | — | same-status notes-append без проверки актора — удалить ветку |
| `A10-INT-14` | P3 | actionable | found-2026-10-24 | AUD10-CODE | — | bot | — | pending-исполнитель по инвайту; mgr_delete_ по env; notify_superadmins при assign_role(manager) |
| `A10-INT-15` | P3 | actionable | found-2026-10-24 | AUD10-CODE | — | api | — | тест SEC-06 в регистрации |
| `A10-SAT-03` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | media-service, provisioning | — | media под ролью-владельцем с DDL — роль uk_media_app, DDL только в media-migrate (с A9-P3-33) |
| `A10-SAT-04` | P3 | deferred | decision-2026-10-24 | AUD10-CODE | — | media-service, access-api, api | — | общий X-API-Key media без scope — принятый риск до A10-SAT-03 |
| `A10-SAT-10` | P3 | actionable | found-2026-10-23 | AUD10-CODE | — | api, frontend | — | лицевой счёт в query-string — POST с телом, account не в URL страницы |
| `A10-EXT-03` | P3 | deferred | verified-edge-2026-10-23 | AUD10-EXT | — | asset-web | — | assets.profk.uz: script-src unsafe-inline (asset-bot, вне репо) |
| `A10-HOST-05` | P2 | deferred | verified-host-2026-10-23 | AUD10-EXT | — | InfraSafe compose | — | внешнее репо infrasafe: PostGIS=PG 15.4, wireguard:latest privileged, mosquitto:latest, alloy с docker.sock |
| `A10-HOST-10` | P3 | deferred | verified-host-2026-10-23 | AUD10-EXT | — | edge | — | внешнее репо infrasafe: nginx.profk.conf правлен на месте + .bak; закоммитить |
| `A10-HOST-04` | P2 | deferred | owner-decision-2026-10-24 | AUD10-HOST | — | хосты, Telegram | — | токен @profk_monitoring_bot был в bash_history (живой); истории очищены, HISTIGNORE; ротацию владелец решил не делать |
| `A10-HOST-06` | P3 | decision | verified-host-2026-10-23 | AUD10-HOST | — | хост profk | — | NOPASSWD sudo, ключ в /root, PermitRootLogin yes в основном sshd_config — выровнять с 105 или принять |
| `A10-HOST-07` | P3 | actionable | verified-host-2026-10-23 | AUD10-HOST | — | compose, хосты | — | uk-internal на 105; payment-* в uk-internal на profk; пересоздание в окне HOST-02/03 |
| `A10-HOST-08` | P3 | actionable | verified-host-2026-10-23 | AUD10-HOST | — | хосты | — | бэкапы .env* со старыми секретами, obs/secrets 644, profk-initdb.sql 644 |
| `A10-HOST-09` | P3 | actionable | verified-host-2026-10-23 | AUD10-HOST | — | хосты | — | fail2ban journalmatch sshd.service vs ssh.service; auditd inactive |
| `A10-HOST-11` | P3 | actionable | verified-host-2026-10-23 | AUD10-HOST | — | Doppler | — | ADMIN_PASSWORD на 105 — 16 символов (profk 64) |
| `A10-INF-09` | P3 | actionable | found-2026-10-23 | AUD10-HOST | — | рабочая машина | — | env.copy*/.env.bak.pr7 на диске; подтвердить плейсхолдеры microservices/* в истории |
| `AUD7-SEC-03` | P2 | decision | verified-2026-09-15 | AUD7-S2 | — | UK API / resource API | — | нужно решение об окне отзыва в существующем RBAC-плане; RBAC-план от 2026-09-05 в main отсутствует — сначала AUD7-DOC-01 |
| `AUD8-DB-02` | P3 | deferred | verified-2026-09-19 | AUD8-C1 | — | — | — | OFFSET-пагинация; deferred до триггера p95>300 мс / >50k строк |
| `AUD8-ENG-02` | P3 | decision | verified-2026-09-19 | AUD8-E1 | — | — | — | BACKUPS.md: дампы plaintext; ключи/cron на хостах — решение владельца |
| `A9-P3-29` | P3 | actionable | found-2026-09-23 | AUD9-W5 | — | access-api, edge | — | Включение `ACCESS_COMMAND_RECLAIM_ENABLED` заблокировано проверкой персистентного дедупа edge-агента |
| `A9-P3-33` | P3 | actionable | found-2026-09-23 | AUD9-W7 | — | media-service | — | media: перевод на alembic; bootstrap новой площадки падает на 0001; сверить pre_0001.sql с прод-БД |
| `A9-P3-39` | P3 | actionable | found-2026-09-28 | AUD9-W7 | — | media-service, api, access-api | — | media: отложенные находки ревью 2026-09-28 (права ключей, rate limit, контрактный тест, мелочи) |
| `A9-P2-24` | P2 | actionable | audit9-2026-09-22 | AUD9-W8 | — | media-service, bot | — | Чистка media_service: SDK и то, чем не пользуются ни код, ни владелец (поиск — оставить) |
| `A9-P2-26` | P2 | deferred | owner-decision-2026-09-23 | AUD9-W8 | — | bot, БД | — | Чистка: в `access_rights` никто не пишет, а UI карточки прав её читает |
| `AUD5-JUNK-5` | P3 | no-pr | verified-2026-09-11 | П7 | — | — | — | локальные venv/db/png — только пофайлово с подтверждения; 2026-09-11: uk_management_bot/venv 152 МиБ, 37 PNG 7,1 МиБ, ruvector.db 1,5 МиБ; корневой .venv 249 МБ (09-09) |
| `ARCH-06` | P2 | deferred | verified-2026-09-11 | — | — | — | — | AST-граф 2026-09-11: 0 циклов services↔utils; возвращаться вместе с развязкой границы (AUD5-ARCH-4/A7) |
| `PENT-F13` | P3 | deferred | owner-decision-2026-09-18 | — | — | DNS/регистратор владельца (оба домена) | — | решение владельца 2026-09-18: CAA на текущем DNS-провайдере не реализуем — deferred до смены провайдера (тогда CAA + DNSSEC, проверять раздельно CAA и DS); OCSP stapling неприменим для Let's Encrypt (закрыто ранее) |
| `SEC-115` | P3 | deferred | verified-2026-09-11 | — | — | — | — | UK-часть сделана (/api/uk-buildings-metrics + x-service-token при INFRASAFE_INVENTORY_TOKEN); остаток внешний — принуждение auth на стороне InfraSafe и проверка токена на продах |

## Спорные пункты, разведённые явно

_История разведения (что и когда решили); текущее состояние — в таблицах выше._

- `REG-03` — был закрыт кодом, но открыт документом; подтверждён чтением
  `ci.yml` и закрыт 2026-07-26. Пример класса «код впереди документа».
- `AUD5-APIFE-2` — закрыт PR #263, документ поправлен PR #264.
- `PENT-F04` — основная часть закрыта раньше; календарный остаток
  (query-токен WS) снят 2026-08-30 (PR #516).
- `AUD3-37` — не назывался в первых версиях плана, шёл как `decision`;
  закрыт 2026-08-07 (Программа B, парой с `AUD5-CODE-6`).
- `PENT-F13`, `PENT-F14`, `PENT-F15`, `PENT-F16` — каждый отдельной строкой:
  сокращение группы «F12/F13/F15/F16» ранее скрыло потерю `PENT-F14`.
  F14/F15/F16 закрыты 2026-09-02; открыт только `PENT-F13` (CAA + DNSSEC у регистратора).
- `AUD5-PRAC-3` и `AUD3-38` — дубль друг друга; закрыты парой 2026-07-27.
