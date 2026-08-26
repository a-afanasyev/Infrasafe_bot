# UK Management — архитектурные схемы

> _Последнее редактирование: 2026-08-25_

> Диаграммный компаньон к [ARCHITECTURE.md](ARCHITECTURE.md): контейнеры и их
> зависимости, модульная структура каждого сервиса, потоки данных и ER-схемы
> всех баз данных. Источник истины — код (`docker-compose*.yml`, модели
> SQLAlchemy, роутеры). Текстовые регламенты доменов — [REQUESTS.md](REQUESTS.md),
> [SHIFTS_AND_ASSIGNMENT.md](SHIFTS_AND_ASSIGNMENT.md), [DATA_MODEL.md](DATA_MODEL.md).

---

## 1. Общая схема системы (контейнеры и внешние зависимости)

```mermaid
flowchart TB
    subgraph ext[Внешний мир]
        TG[Telegram Bot API]
        ANTH[Anthropic API\nClaude Haiku - классификатор]
        USERS[Жители / персонал / охрана]
        INFRA[Портал InfraSafe\nwebhooks HMAC]
        DOPPLER[Doppler\nсекреты всех сервисов]
        OBS[Observability-хост\nPrometheus + Alloy + Grafana]
    end

    EDGE["Edge nginx InfraSafe\ninfrasafe.uz / profk.uz\nprefix-allowlist SEC-22"]

    subgraph host[Прод-хост · docker-сеть uk-network · порты только 127.0.0.1]
        BOT["uk-management-bot (app)\naiogram 3 · 1 воркер\nосновной бот: жители+персонал"]
        GIB["uk-group-intake-bot\nотдельный токен · polling групп\nLLM-приём заявок (флаг)"]
        API["uk-management-api\nFastAPI REST + WS · :8085→8080\npreflight схемы на старте"]
        ACC["uk-access-api\nFastAPI · ANPR/пропуска · :8087→8080"]
        FRONT["uk-frontend\nnginx + React build · :3002→80\nбренд = build-arg VITE_BRAND"]
        MEDIA["uk-media-service\nFastAPI · :8009→8000\npreview-cache на диске"]
        RAPI["uk-resource-api\nFastAPI · :8100\nучёт ресурсов (мульти-тенант)"]
        RWORK[uk-resource-worker\nфоновые задачи ресурсов]
        PG[("uk-postgres · PG15\nБД uk_management|profk_management\n+ логическая БД uk_media")]
        REDIS[("uk-redis · Redis 7\nrate-limit · pub/sub · pending-кандидаты\nnonce-store · WS-брокер")]
        RPG[("uk-resource-postgres · PG16\nБД учёта ресурсов")]
    end

    USERS -->|HTTPS| EDGE
    USERS -->|Telegram| TG
    TG <--> BOT
    TG <--> GIB
    GIB -->|classify structured output| ANTH

    EDGE -->|/uk/ статика| FRONT
    EDGE -->|/uk/api/*| API
    EDGE -->|/uk/api/access/*| ACC
    EDGE -->|/uk/api/resource/*| RAPI

    BOT --> PG & REDIS
    BOT -->|X-API-Key| MEDIA
    GIB --> PG & REDIS
    GIB -->|фото групп| MEDIA
    GIB -.->|уведомления от лица основного бота| TG
    API --> PG & REDIS
    API -->|media-proxy signed-URL| MEDIA
    API -->|s2s launch-ticket| RAPI
    API <-->|outbox / inbox HMAC| INFRA
    ACC --> PG & REDIS
    ACC -->|фото проездов| MEDIA
    MEDIA --> PG
    MEDIA -->|скачивание оригиналов| TG
    RAPI --> RPG
    RWORK --> RPG

    DOPPLER -.->|doppler run -- при деплое| host
    OBS -.->|scrape /metrics + docker-health| host
```

One-shot-контейнеры (не на схеме): `provision-roles` → `migrate` (основная
схема, alembic head `014`), `media-migrate` (`uk_media`),
`resource-provision-roles` → `resource-migrate` (ресурсы).

**Матрица «кто с кем говорит»:**

| Клиент → Сервис | postgres | redis | media | resource-api | Telegram | Anthropic | InfraSafe |
|---|---|---|---|---|---|---|---|
| app (основной бот) | RW | RW | API-key | — | polling | — | — |
| group-intake-bot | RW | RW (pending/dedup/rate) | API-key | — | polling (свой токен) + send основным | classify | — |
| api | RW | RW (pub/sub, rate) | proxy | s2s ticket | send (OTP, уведомления) | — | outbox→ / ←inbox |
| access-api | RW | RW (nonce, WS-брокер) | API-key | — | — | — | — |
| media-service | RW (только uk_media) | — | — | — | download file_id | — | — |
| resource-api/worker | — | — | — | — | — | — | — |
| frontend | — | — | — | — | — | — | — (статика, всё через edge→api) |

---

## 2. Модульная структура основного приложения

### 2.1 Telegram-бот (`uk_management_bot/`)

```mermaid
flowchart LR
    subgraph MW[Middlewares]
        AUTH[auth: identity+роли\nтихий group-path]
        ROLE[role_mode]
        THR[throttling in-memory]
    end
    subgraph H["Handlers (роутеры aiogram)"]
        GI[group_intake\nпервый, catch-all групп]
        REQ[requests / создание,\nстатусы, комментарии, отчёты]
        ASSIGN[admin: assignment,\nreassignment, views]
        SHIFTS[shifts, my_shifts,\nshift_management, transfer]
        EMP[employee_management,\nuser_management, rename]
        VERIF[user_verification,\napartments, yards]
        ACCH[access_control\nгостевые коды]
        MISC[onboarding, profile,\nfeedback, inspector, ...]
    end
    subgraph S["Services (бизнес-логика)"]
        WF["request_workflow канон\nguards → specs → planner\nодин писатель plan_transition"]
        RSVC[request_service,\nsave_request]
        DISP[dispatch / auto_manager\nrule engine дежурных]
        SHS[shift_service,\nshift_scheduler 11+1 джоб]
        NOTIF[workflow_notifications\nнотифай-интенты]
        MEDIA_S[completion_media SSOT,\nmedia_client]
        GIS[group_intake:\nprefilter, classifier, pending]
        ADDR[request_address,\naddress_service]
    end
    subgraph U["Utils / канон"]
        SPEC[specializations\nmatches_required_specs]
        CAT[constants/categories\ncategory→specialization]
        ENUMS[enums, constants\nстатусы канон]
        LOC["get_text (ru/uz)"]
    end
    DB[(SQLAlchemy models\n33 таблицы)]

    MW --> H --> S --> DB
    S --> U
    H --> U
```

Точки сборки: `main.py` (основной бот: `setup_dispatcher` = middlewares +
роутеры; health-сервер :8000) и `group_intake_main.py` (отдельный процесс
group-intake-бота: только группа-роутер + свой polling).

### 2.2 REST/WS API (`uk_management_bot/api/`)

| Префикс | Роутер | Назначение |
|---|---|---|
| `/api/v2/auth` | auth | Widget/TWA/пароль+MFA, refresh-ротация, cookie |
| `/api/v2/requests` | requests, stats | CRUD заявок, канон-переходы (PATCH), канбан |
| `/api/v2/callcenter` | callcenter | Приём обращений оператором |
| `/api/v2/profile` | profile | Профиль текущего пользователя |
| `/ws/v2` | ws | Live-обновления (канбан, доступ) |
| `/api/v2/shifts` | shifts (+employees) | Смены, сотрудники, инвайты, активация |
| `/api/v2/executor/shifts` | executor_shifts | Смены глазами исполнителя |
| `/api/v2/addresses` | addresses | Справочник двор/дом/квартира |
| `/api/v2/residents` | residents, verification, documents | Жители, модерация, документы |
| `/api/v2/public` | public, work-reports public | Табло, витрина «до/после» (без auth) |
| `/api/v2/board-config` | board_config | Конфиг табло |
| `/api/v2/auto-manager` | auto_manager | Тумблер и правила авто-назначения |
| `/api/v2/webhooks` | webhooks | Входящие InfraSafe (inbox) |
| `/api/v2/registration` | registration | WebApp-регистрация жителя |
| `/api/v2/feedback` | feedback | Обратная связь |
| `/api/v2/monitored-groups` | monitored_groups | Реестр групп Group Intake |
| `/api/v2/materials` | materials | Склад (FIFO) |
| `/api/v2/work-reports` | work_reports | Модерация витрины (менеджер) |
| `/api/v2/resource-accounting` | resource_accounting | s2s-ticket, TWA-ticket |
| прочее | health, announcements, media(proxy) | Health, объявления, signed-media |

### 2.3 Frontend SPA (`frontend/`)

```mermaid
flowchart TB
    subgraph PUB[Публичные маршруты]
        LOGIN[/login/]
        BOARD[/resident-board — табло/]
        WR[/work-reports — витрина до-после/]
        REG[/register — WebApp регистрации/]
        TWA[/twa/* — Mini App/]
    end
    subgraph DASH["/dashboard (ProtectedRoute: admin|manager)"]
        KAN[Канбан заявок]
        AN[analytics]
        SH[shifts · templates]
        EMPP[employees · employees/:id]
        ADR[addresses]
        RES[residents · residents/:id]
        GRP["groups (Group Intake)"]
        BE[board-editor]
        WRM[work-reports модерация]
        FB[feedback]
    end
    subgraph MODULES[Модульные разделы со своими ролями]
        ACCX["/dashboard/access/* — live охраны,\nhistory, database, equipment\n(security_operator, system_admin, manager)"]
        MAT[/dashboard/materials/]
        RA["/dashboard/resource-accounting\n(build-флаг VITE_RESOURCES_ENABLED)"]
    end
    APIC[apiClient axios\ncookie uk_access · WS]
    PUB --> APIC
    DASH --> APIC
    MODULES --> APIC
```

### 2.4 Пайплайн Group Intake (сообщение группы → заявка)

```mermaid
flowchart TD
    MSG[Сообщение в группе] --> F1{Флаг включён?\nне бот / не via_bot?}
    F1 -->|нет| SILENT[Тишина]
    F1 --> CT[candidate_text ≤2000\nтекст или caption]
    CT --> CMD{Команда?}
    CMD -->|да| SILENT
    CMD --> TAG{"Тег #заявка/#ariza?"}
    TAG -->|есть| REG
    TAG -->|нет| PRE{Префильтр\nдлина/маркеры/фото}
    PRE -->|отсев| SILENT
    PRE --> REG{Группа в реестре\nи активна?}
    REG -->|нет| SILENT
    REG --> TGATE{Тег-режим и тега нет?}
    TGATE -->|да| SILENT
    TGATE --> KIND{kind}
    KIND -->|staff| STAFF{Автор approved\nexecutor/inspector/manager?}
    STAFF -->|нет| SILENT
    KIND -->|residents| DED
    STAFF --> PH{"Фото? (видео/кружок)"}
    PH -->|видео| PHOTOMSG[Просьба прислать фото]
    PH --> DED[Дедуп + rate-limit LLM]
    DED --> LLM{"LLM classify\n(тег переопределяет NOT_REQUEST)"}
    LLM -->|NOT_REQUEST| SILENT
    LLM -->|PROCESSING_ERROR| LOGGED[Тишина + лог-маркер]
    LLM -->|REQUEST| ADDRM["Адресный матчер:\nквартиры автора (residents)\nдом/двор по тексту (staff)\nтранслит + токены"]
    ADDRM -->|нет адреса| INVITE[Приглашение в личный бот\ncooldown 1/час]
    ADDRM -->|1..4 кандидата| PROMPT["Промпт: Да / Нет / Другой адрес\n(staff: выбор адреса, любой сотрудник)"]
    PROMPT -->|Да + ре-гейт| SAVE[save_request\nstaff: acceptance_mode=manager\nreported_by=автор]
    SAVE --> NUM[Ответ с номером YYMMDD-NNN]
    PROMPT -->|час тишины| EXPIRE[Кандидат протухает]
```

---

## 3. Схемы баз данных

Четыре независимых хранилища:

| БД | Инстанс | Владелец схемы | Runtime-роль | Таблиц |
|---|---|---|---|---|
| `uk_management` / `profk_management` | uk-postgres (PG15) | `uk_migration_owner` (alembic, head 014) | `uk_bot_runtime`, `uk_api_runtime`, `uk_access_runtime` | 33 ORM + 22 access |
| `uk_media` | тот же uk-postgres | `uk_media_owner` | та же (create_all) | 4 |
| ресурсы | uk-resource-postgres (PG16) | `resource` | `resource_app` | 17 |
| Redis | uk-redis | — | — | ключи: `gint:*`, rate, pub/sub, nonce |

### 3.1 Основная БД — домен «Пользователи и доступ к системе»

```mermaid
erDiagram
    users ||--o{ user_documents : "документы"
    users ||--o{ user_verifications : "верификация"
    users ||--o{ access_rights : "уровень подачи заявок"
    users ||--o{ refresh_tokens : "веб-сессии"
    users ||--o{ invite_nonces : "инвайты сотрудников"

    users {
        int id PK
        bigint telegram_id UK
        text roles "JSON: applicant/executor/manager/inspector/admin/..."
        varchar active_role
        varchar status "pending/approved/blocked"
        varchar verification_status
        text specialization "JSON/CSV: канон-словарь + universal"
        varchar language "ru/uz"
        varchar email UK
        varchar password_hash
        timestamptz deleted_at "soft-delete"
    }
    refresh_tokens {
        int id PK
        int user_id FK "CASCADE"
        varchar token_hash UK "SHA-256, ротация"
        timestamptz revoked_at
    }
    invite_nonces {
        int id PK
        varchar nonce UK "одноразовый HMAC-токен"
        varchar role
        text specializations
    }
```

### 3.2 Основная БД — домен «Заявки» (ядро)

```mermaid
erDiagram
    users ||--o{ requests : "автор user_id"
    users |o--o{ requests : "исполнитель executor_id"
    users |o--o{ requests : "докладчик reported_by_user_id (staff)"
    requests ||--o{ request_comments : ""
    requests ||--o{ request_assignments : "история назначений"
    requests ||--o| ratings : "оценка 1:1"
    apartments |o--o{ requests : ""
    buildings |o--o{ requests : "RESTRICT"
    yards |o--o{ requests : "RESTRICT"
    monitored_groups |o..o{ requests : "происхождение source_chat_id (без FK)"

    requests {
        varchar request_number PK "YYMMDD-NNN (строка!)"
        int user_id FK
        int executor_id FK
        varchar category "канон-ключи"
        varchar status "Новая/В работе/Закуп/Уточнение/Выполнена/Исполнено/Принято/Возвращена/Отменена"
        varchar urgency "low/medium/high/critical"
        varchar source "bot/twa/group/webhook/callcenter"
        varchar address_type "CHECK: ровно один FK"
        int apartment_id FK
        int building_id FK
        int yard_id FK
        json media_files
        bigint source_chat_id "Group Intake"
        bigint source_message_id
        int reported_by_user_id FK "SET NULL"
        varchar acceptance_mode "CHECK resident|manager"
        bool manager_confirmed
        timestamptz completed_at
    }
    request_assignments {
        int id PK
        varchar request_number FK
        varchar assignment_type "individual/group"
        int executor_id FK
        varchar group_specialization
        varchar status "active/cancelled/completed · partial-unique active"
    }
    ratings {
        int id PK
        varchar request_number FK "UNIQUE"
        int rating "1-5"
    }
    request_number_counters {
        varchar day_prefix PK "YYMMDD"
        int last_seq "gap-safe"
    }
    monitored_groups {
        int id PK
        bigint chat_id UK
        varchar kind "residents|staff"
        bool is_active
        bool require_tag "тег-режим"
        int created_by FK
        int updated_by FK
    }
```

### 3.3 Основная БД — домен «Смены»

```mermaid
erDiagram
    users ||--o{ shifts : "исполнитель"
    shift_templates |o--o{ shifts : "шаблон"
    shifts ||--o{ shift_assignments : "AI-скоринг работ"
    requests ||--o{ shift_assignments : ""
    shifts ||--o{ shift_transfers : "передачи"
    shift_schedules ||..o{ shifts : "планирование по датам"

    shifts {
        int id PK
        int user_id FK
        timestamptz start_time
        timestamptz end_time "NULL = ad-hoc, закрывает человек"
        varchar status "planned→active (авто-джоба 3 мин) →completed"
        text specialization_focus "требование смены + universal"
        int shift_template_id FK
    }
    shift_templates {
        int id PK
        varchar name
        text required_specializations
    }
    shift_schedules {
        int id PK
        date date UK "одно расписание на дату"
        varchar status
    }
    shift_transfers {
        int id PK
        int shift_id FK
        int from_executor_id FK
        int to_executor_id FK
        varchar status "pending/assigned/accepted/rejected/..."
        varchar reason "illness/emergency/workload/vacation/other"
    }
```

### 3.4 Основная БД — домен «Адреса», «Коммуникации», «Материалы», «Витрина»

```mermaid
erDiagram
    yards ||--o{ buildings : CASCADE
    buildings ||--o{ apartments : CASCADE
    users ||--o{ user_apartments : "модерация pending/approved"
    apartments ||--o{ user_apartments : ""
    users ||--o{ user_yards : "доп. дворы"

    users ||--o{ notifications : ""
    users |o--o{ audit_logs : "переживает удаление (telegram_user_id)"
    users ||--o{ feedback : ""
    board_config ||..|| board_config : "singleton id=1"
    webhook_outbox ||..|| webhook_outbox : "transactional outbox claim/lease"
    webhook_inbox ||..|| webhook_inbox : "дедуп UNIQUE event_id"

    materials ||--o{ material_receipts : "партии FIFO"
    materials ||--o{ material_issues : "списания"
    material_issues ||--o{ material_issue_allocations : ""
    material_receipts ||--o{ material_issue_allocations : "лот-источник"

    work_reports {
        int id PK
        varchar request_number UK "снапшот, НЕ FK"
        varchar category_key
        varchar address_public "без квартир"
        json before_media_ids "id в uk_media"
        json after_media_ids
        varchar status "pending/published/... сага с media"
        int moderated_by FK
    }
```

### 3.5 Основная БД — домен access_control (СКУД/ANPR, 22 таблицы)

Отдельный сервис, raw-DDL (без ORM в `database/models/`). Группами:

```mermaid
erDiagram
    parking_zones ||--o{ access_gates : "въезды"
    access_gates ||--o{ access_cameras : ""
    access_gates ||--o{ access_barriers : ""
    edge_controllers ||--o{ access_cameras : "обслуживает"
    edge_controllers ||--o{ access_barriers : ""
    edge_controllers ||--o{ controller_sync_events : "offline-snapshot Ed25519"
    parking_zone_yards }o--|| parking_zones : ""

    vehicles ||--o{ vehicle_apartments : "машина↔квартира"
    apartments ||--o{ vehicle_apartments : ""
    vehicles ||--o{ access_passes : "пропуска"
    resident_access_requests }o--|| users : "заявки жителей + гостевые коды"

    camera_events ||--o| access_decisions : "решение по событию"
    access_decisions ||--o{ barrier_commands : "команды шлагбауму"
    access_decisions ||--o{ access_events : "журнал проездов"
    access_events ||--o{ access_entry_confirmations : "подтверждение охраной"
    vehicles ||--o{ vehicle_presence_sessions : "кто на территории"
    manual_openings }o--|| access_barriers : "ручные открытия"
    access_audit_logs }o--|| users : "аудит операторов"

    parking_spots }o--|| parking_zones : ""
    parking_spots ||--o{ parking_spot_assignments : "закрепление за квартирой"
```

Ключевые правила: анти-replay nonce и WS-брокер — в Redis
(multi-worker-safe); фото проездов — в media-service (вне «горячего» пути);
правила доступа (`access_rules`) вычисляют решение при событии камеры.

### 3.6 БД `uk_media` (media-service)

```mermaid
erDiagram
    media_channels ||--o{ media_files : "канал-источник"
    media_files ||--o{ media_tags : "теги (request_number, роль фото)"
    media_upload_sessions ||..o{ media_files : "загрузки"

    media_files {
        int id PK
        varchar file_id "Telegram file_id"
        varchar file_type
        varchar publication_lock "сага work-reports"
    }
    media_tags {
        int id PK
        int media_file_id FK
        varchar tag "request:NNN / before / after / ..."
    }
```

Файлы физически живут в Telegram; media-service хранит метаданные, скачивает
оригиналы по требованию и держит дисковый preview-cache (~480px JPEG, LRU по
заявке).

### 3.7 БД учёта ресурсов (resource-accounting, PG16)

```mermaid
erDiagram
    tenants ||--o{ users : "мульти-тенантность"
    tenants ||--o{ resource_objects : ""
    object_types ||--o{ resource_objects : ""
    resource_objects ||--o{ meter_object_links : ""
    meters ||--o{ meter_object_links : ""
    providers ||--o{ meters : "поставщик ресурса"
    meters ||--o{ readings : "показания"
    readings ||--o{ reading_revisions : "правки с историей"
    reporting_periods ||--o{ readings : ""
    anomaly_rules }o--|| tenants : "правила аномалий"
    exports ||--o{ export_rows : "выгрузки Excel"
    launch_tickets }o--|| users : "s2s одноразовый вход из основного API"
    tags ||--o{ meter_tags : ""
    tags ||--o{ object_tags : ""
```

### 3.8 Redis (не БД, но контракт ключей)

| Префикс | Назначение | TTL |
|---|---|---|
| `gint:cand:{chat}:{msg}` | pending-кандидат Group Intake (payload) | 1 ч |
| `gint:seen:{chat}:{msg}` | дедуп обработанных сообщений | 24 ч |
| `gint:llm:{chat}` | rate-limit LLM (6/мин) | 1 мин |
| `gint:invite:{tg_id}` | cooldown приглашений | 1 ч |
| pub/sub каналы | realtime заявок (канбан), access-события | — |
| nonce access | анти-replay device-auth | короткий |
| rate-limit auth/API | fail-closed гварды | скользящий |

---

## 4. Сквозной поток: заявка из staff-группы до «Принято»

```mermaid
sequenceDiagram
    actor S as Сотрудник
    participant G as Telegram-группа
    participant GIB as group-intake-bot
    participant LLM as Anthropic
    participant DB as uk-postgres
    participant M as media-service
    participant BOT as основной бот
    participant API as api
    participant D as Дашборд (менеджер)

    S->>G: фото + "#заявка адрес, описание"
    G->>GIB: update (polling, свой токен)
    GIB->>DB: реестр группы, staff-гейт автора
    GIB->>LLM: classify(text) [тег переопределяет NOT_REQUEST]
    GIB->>DB: адресный матчер (дом/двор, транслит)
    GIB->>G: "Похоже на заявку... [Да/Нет]" / выбор адреса
    S->>G: Да (любой approved-сотрудник)
    GIB->>M: upload фото (X-API-Key)
    GIB->>DB: save_request: acceptance_mode=manager, reported_by=автор
    GIB->>G: "Заявка N создана"
    Note over DB: outbox-событие + notify-интенты в той же транзакции
    D->>API: назначить исполнителя (фильтр по специализации)
    API->>DB: канон MANAGER_ASSIGN → "В работе"
    BOT-->>S: уведомления исполнителю/докладчику (RU/UZ)
    Note over BOT: исполнитель ведёт: Закуп/Уточнение → Выполнена (фото в media)
    D->>API: "Подтвердить" (MANAGER_CONFIRM)
    API->>DB: acceptance_mode=manager → сразу "Принято" (терминально)
    API-->>D: realtime (Redis pub/sub → WS) — канбан обновился
```

---

## 5. Развёртывание и окружения

| Артефакт | infrasafe/105 | profk |
|---|---|---|
| Compose | `-f docker-compose.yml -f docker-compose.media.yml` | `-f docker-compose.yml -f docker-compose.profk.yml` (тонкий override, оба -f обязательны) |
| БД | `uk_management` | `profk_management` |
| Бренд фронта | `infrasafe` | `VITE_BRAND=profk` |
| Group Intake | выключен | включён (profile `group-intake`) |
| Секреты | Doppler config `infrasafe` | Doppler config `profk` |
| Деплой | build 4 образа → migrate → up (по одному, `--no-deps --wait`) → frontend отдельно → тег `<host>-YYYY-MM-DD` | так же |

Наблюдаемость (отдельный хост): Prometheus (rules/alerts) + Grafana; Alloy на
прод-хостах шлёт метрики remote-write (uk_api scrape — под
`HEALTH_METRICS_TOKEN`); systemd-таймер docker-health раз в минуту сверяет
фактические контейнеры с инвентарём (`expected-containers.tsv`,
`inventory.yml`) — незаявленный контейнер = алерт P2.

---

## 6. Связанные документы

- [ARCHITECTURE.md](ARCHITECTURE.md) — текстовая архитектура (потоки, auth, медиа).
- [DATA_MODEL.md](DATA_MODEL.md) — инварианты модели данных по доменам.
- [../product/PRD.md](../product/PRD.md) — продуктовое ТЗ.
- [../product/OVERVIEW.md](../product/OVERVIEW.md) — бизнес-обзор.
- `.claude/skills/uk-deploy/SKILL.md` — деплой-runbook (роли БД, Doppler, ротации).
