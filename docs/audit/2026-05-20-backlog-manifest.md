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

- пунктов всего (с Priority): **485**
- закрыто маркером: **449**
- открыто маркером: **36**

  - `actionable` — **28**
  - `decision` — **1**
  - `no-pr` — **1**
  - `deferred` — **6**

Из них actionable по приоритету: P1=3, P2=18, P3=7.

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
| `AUD3-07` | P2 | deferred | gate-2026-09-01 | A2 | — | — | — | ратчет построен 2026-09-01: test_aud307_unconverted_ratchet, baseline 23 файла / 232 сайта, двунаправленный; конверсия «при касании», deferred-трекер класса |
| `AUD5-CODE-10` | P3 | deferred | gate-2026-09-01 | A5 | — | — | — | ратчет построен 2026-09-01: test_aud5_code10_long_functions_ratchet, baseline 40 файлов / 49 функций, двунаправленный; раскрой «при касании» под принуждением гейта |
| `AUD5-ARCH-4` | P2 | deferred | gate-2026-08-09 | A7 | — | — | — | гейт границы стоит (test_aud5_arch4_domain_boundary_gate); развязка (L) — только при намерении разносить сервисы |
| `AUD7-CODE-03` | P2 | actionable | verified-2026-09-09 | AUD7-B1 | — | bot / Redis / PostgreSQL | — | из отчёта CODE-03; AC и зависимости в канонической записи |
| `AUD7-CODE-04` | P2 | actionable | verified-2026-09-09 | AUD7-B1 | — | bot / Redis | — | из отчёта CODE-04; AC и зависимости в канонической записи |
| `AUD7-ARCH-02` | P3 | actionable | verified-2026-09-11 | AUD7-C1 | — | UK services | — | импортируются сервисные функции api.*.service / схемы, не HTTP; ограниченный перенос, цикла нет |
| `AUD7-SIMP-01` | P3 | actionable | verified-2026-09-11 | AUD7-C1 | — | bot image / locales | — | 9 файлов на месте: 26 419 строк / 1 928 925 байт; ссылка на Dockerfile исправлена (:54) |
| `AUD7-SIMP-02` | P3 | actionable | verified-2026-09-09 | AUD7-C1 | — | bot states / keyboards | — | из отчёта SIMP-02; AC и зависимости в канонической записи |
| `AUD7-SIMP-03` | P3 | actionable | verified-2026-09-09 | AUD7-C1 | — | UK work_reports / tests | — | из отчёта SIMP-03; AC и зависимости в канонической записи |
| `AUD7-DEP-01` | P3 | actionable | verified-2026-09-11 | AUD7-E1 | — | frontend dev dependencies | — | npm audit 2026-09-11: prod 0, dev 10 package entries (high 4) — не 10 уникальных CVE; новые GHSA у vitest, baseline-browser-mapping, js-yaml; всё dev-only |
| `AUD7-ENG-01` | P2 | actionable | verified-2026-09-11 | AUD7-E1 | — | frontend CI | — | невалидный JSON уже exit 1; fail-open только для валидного {error}/{} — нужна проверка структуры отчёта |
| `AUD7-ENG-02` | P2 | actionable | verified-2026-09-09 | AUD7-E1 | — | E2E CI | — | из отчёта ENG-02; AC и зависимости в канонической записи |
| `AUD7-ENG-03` | P2 | actionable | verified-2026-09-09 | AUD7-E1 | — | media / resource / payment | — | из отчёта ENG-03; AC и зависимости в канонической записи |
| `AUD7-ENG-04` | P2 | actionable | verified-2026-09-09 | AUD7-E1 | — | payment CI | — | из отчёта ENG-04; AC и зависимости в канонической записи |
| `AUD7-ENG-05` | P2 | actionable | verified-2026-09-09 | AUD7-E1 | — | Makefile / runbook | — | из отчёта ENG-05; AC и зависимости в канонической записи |
| `AUD7-ENG-06` | P2 | actionable | verified-2026-09-09 | AUD7-E1 | — | dev compose / README | — | в .env.example нет RESOURCE_POSTGRES_PASSWORD / RESOURCE_APP_PASSWORD / RESOURCE_SESSION_SECRET, compose требует их через :? — config падает до старта postgres/redis |
| `AUD7-CODE-01` | P2 | actionable | verified-2026-09-09 | AUD7-F1 | — | frontend / UK auth | — | из отчёта CODE-01; AC и зависимости в канонической записи |
| `AUD7-CODE-02` | P2 | actionable | verified-2026-09-11 | AUD7-F1 | — | frontend | — | воспроизведено 2026-09-11: cleanup → отложенный close → таймер → второй сокет; ссылка на тест исправлена (:26) |
| `AUD7-CODE-05` | P2 | actionable | verified-2026-09-09 | AUD7-F1 | — | frontend | — | из отчёта CODE-05; AC и зависимости в канонической записи |
| `AUD7-CODE-06` | P2 | actionable | verified-2026-09-11 | AUD7-F1 | — | frontend / UK employees API | — | EmployeesPage после PR #556 уже с серверной пагинацией и настоящим total; дыра только в пикерах смен (CreateShiftModal берёт дефолт limit=50) — AC сужен |
| `AUD7-ARCH-01` | P2 | actionable | verified-2026-09-09 | AUD7-M1 | — | media API | — | из отчёта ARCH-01; AC и зависимости в канонической записи |
| `AUD7-ENG-07` | P2 | actionable | verified-2026-09-09 | AUD7-O1 | — | DB / operations | — | прод УЖЕ дампит все БД (кросс-бэкап profk↔105: 5 БД на profk, 4 на 105, payment с 2026-09-06); evidence-скрипты в репо мёртвые; остаток — реестр RPO/RTO в docs/ops + restore-rehearsal + списание scripts/backup-db.sh |
| `AUD7-ENG-08` | P3 | actionable | verified-2026-09-09 | AUD7-O1 | — | resource image | — | из отчёта ENG-08; AC и зависимости в канонической записи |
| `AUD7-COR-01` | P1 | actionable | verified-2026-09-11 | AUD7-R1 | — | resource API | — | воспроизведено 2026-09-11: после error→ok Mar consumption=150 вместо 50, Apr 250 вместо 100; тест ok→ok цепочку не ловит |
| `AUD7-COR-02` | P1 | actionable | verified-2026-09-11 | AUD7-R1 | — | resource API / frontend | — | воспроизведено 2026-09-11: not_entered=1 / can_submit=false, submit всё равно → submitted; UI тоже пропускает |
| `AUD7-COR-03` | P1 | actionable | verified-2026-09-11 | AUD7-R1 | — | resource API / PostgreSQL | — | воспроизведено 2026-09-11 на двух SQLite-сессиях (поздняя запись поверх submitted); PostgreSQL concurrency-тест обязателен |
| `AUD7-SEC-02` | P2 | actionable | verified-2026-09-11 | AUD7-S1 | — | access API | — | handshake без DB identity-check (только JWT roles/exp), первая DB-проверка — после первого интервала recheck; фикс = общий предикат ДО стрима и в watcher |
| `AUD7-SEC-04` | P2 | actionable | verified-2026-09-09 | AUD7-S1 | — | resource exports | — | из отчёта SEC-04; AC и зависимости в канонической записи |
| `AUD7-SEC-05` | P2 | actionable | verified-2026-09-09 | AUD7-S1 | — | UK auth / Redis | — | из отчёта SEC-05; AC и зависимости в канонической записи |
| `AUD7-SEC-03` | P2 | decision | verified-2026-09-09 | AUD7-S2 | — | UK API / resource API | — | нужно решение об окне отзыва в существующем RBAC-плане; сам RBAC-план от 2026-09-05 не закоммичен — коммитить вместе с консолидацией |
| `TEST-068` | P2 | actionable | verified-2026-09-11 | П11 | — | — | — | срез 2026-09-11: 835 тестов, покрытие 53.52/51.55/43.22/44.70, floors 49/47/39/40; остаток до 80% — components/materials, twa/pages, components/addresses |
| `AUD5-JUNK-5` | P3 | no-pr | verified-2026-09-11 | П7 | — | — | — | локальные venv/db/png — только пофайлово с подтверждения; 2026-09-11: uk_management_bot/venv 152 МиБ, 37 PNG 7,1 МиБ, ruvector.db 1,5 МиБ; корневой .venv 249 МБ (09-09) |
| `ARCH-06` | P2 | deferred | verified-2026-09-11 | — | — | — | — | AST-граф 2026-09-11: 0 циклов services↔utils; возвращаться вместе с развязкой границы (AUD5-ARCH-4/A7) |
| `DB-049` | P2 | deferred | verified-2026-07-27 | — | — | — | — | jsonb+GIN — когда появится запрос по ролям, которому нужен индекс |
| `PENT-F13` | P3 | actionable | verified-2026-09-09 | — | — | DNS/регистратор владельца (оба домена) | — | OCSP stapling неприменим для Let's Encrypt (OCSP-URL в серте нет — проверено); остаток CAA + DNSSEC у регистратора, проверять раздельно (CAA и DS); 2026-09-09: оба пусты на обоих доменах |
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
