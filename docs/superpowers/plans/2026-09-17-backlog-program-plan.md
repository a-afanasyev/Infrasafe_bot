# План работ по бэклогу — после сверки Codex 2026-09-15

## Context

Бэклог `docs/audit/2026-05-20-backlog.md` после разбора сверки 2026-09-15 (снимок `635f97db`): **38 открытых, P1 = 0** — 29 actionable, 2 decision, 6 deferred, 1 no-pr. Три P1 учёта ресурсов закрыты (PR #558), BUG-190 раскатан. Разбор сверки лежит незакоммиченным в основном чекауте.

Цель: довести actionable до нуля волнами PR. Волна = PR → CI → merge → раскатка на оба прода (profk, infrasafe/105) → тег `scripts/tag-deploy.sh <host> --push`. Deferred/decision — не кодовые задачи, а решения владельца (блок в конце).

Оценка: ~95–115 ч кода (один разработчик + Claude, TDD) + ~15 ч хвост TEST-068. Семь волн.

## Правила для всех волн

- TDD: тест RED → фикс → GREEN. Эталон перед мержем — `make test-ci` (оба набора, как CI); фронт — `cd frontend && npm test`; resource — pytest в `resource-accounting/backend` (+ 4 PG-теста в CI).
- Один PR = 1–2 пункта, без попутного рефакторинга. Ветка от main; worktree по желанию (в worktree `frontend/node_modules` — симлинк).
- Закрытие пункта в том же PR: запись в бэклоге (`Resolution` + `✅ CLOSED` в заголовке), строка удаляется из `ASSIGNMENT` в `scripts/backlog_manifest.py`, `python3 -B scripts/backlog_manifest.py --write` и `--check` зелёный.
- Раскатка по `.claude/skills/uk-deploy/SKILL.md`: `build api access-api app migrate` — всегда все четыре (EXPECTED_ALEMBIC_HEAD), `migrate` перед `up`, `--no-deps`; profk — три `-f` (`docker-compose.yml`, `docker-compose.profk.yml`, `docker-compose.payments.yml`), 105 — `docker-compose.yml` + `docker-compose.media.yml`; на profk `doppler` не в PATH неинтерактивного ssh (`export PATH=$HOME/.local/bin:$PATH`), долгую сборку ждать по PID из файла. resource и media — отдельные шаги рунбука. После раскатки — прод-проверка по логам, потом тег.
- Пункты, трогающие одни файлы, идут в один PR или строго последовательно (см. волны). Не бандлить: COR-04 ни с чем; SEC-05 с CODE-01; ENG-03 с ENG-04; ARCH-02 после SIMP-03.

## Волна 0 — зафиксировать разбор (док-PR, 15 мин, без раскатки)

Файлы: `docs/audit/2026-05-20-backlog.md`, `docs/audit/2026-05-20-backlog-manifest.md`, `scripts/backlog_manifest.py`, `docs/audit/2026-09-15-backlog-code-check.md` (untracked → добавить как есть, как отчёт 09-11). Проверка: `--check` → «38 открытых, все распределены». После мержа бэклог в main — канон для волн ниже.

## Волна 1 — корректность и видимые регрессы (~16–20 ч)

**PR-1a `AUD7-COR-04`** (resource, M, 5–7 ч). `resource-accounting/backend/app/services/readings.py` — после `upsert_reading` (:222) вызывать `recompute_forward` (:271) для open/review; PUT/bulk (`api/periods.py:188,211`) и import (`services/imports.py:209`) переводить с `lock_period` на `lock_periods_from` (`services/period_lock.py:53`), чтобы каскад шёл под range-lock. Тест RED: Jan=100, Feb=200, PUT Jan=150 → Feb `previous_value=150`, `consumption=50` (сейчас 100/100); bulk и import — те же ожидания; закрытый период не тронут. Прогон SQLite + PG-набор в CI. QA после раскатки: одна живая ведомость с двумя открытыми месяцами.

**PR-1b `AUD7-CODE-07` → остаток `AUD7-CODE-06`** (frontend, 1.5–2 ч + 6–8 ч; два коммита в одном PR, CODE-07 первым). `frontend/src/hooks/useEmployees.ts`: инвалидации (:102,140,160,181,197,225,243,279) дополнить префиксом `employees-page` (или свести ключи к одному префиксу); тест на настоящем `QueryClient` — блокировка → повторный GET страницы. Затем пикер с серверным поиском/пагинацией (новый компонент поверх `useEmployeesPage`) в шести точках: `components/shifts/CreateShiftModal.tsx:52`, `ShiftDetailModal.tsx:60`, `TransferRequestCard.tsx:36`, `components/kanban/ExecutorPicker.tsx:46`, `components/templates/CreateShiftFromTemplateModal.tsx:51`, `components/employees/DeleteEmployeeModal.tsx:43`. AC CODE-06: при >50 сотрудниках выбирается 51-й и последний.

**PR-1c `AUD7-CODE-08` + `AUD7-CODE-05`** (frontend, 1.5 + 1.5 ч, независимые файлы). CODE-08: `features/resource-accounting/api/types.ts:172` — массивы; `pages/WorksheetPage.tsx:283,285` — `.length` и вывод `meter_number`/сообщения; тест с фактической формой JSON (не числовые моки `WorksheetPage.test.tsx:41`). CODE-05: `pages/ShiftsPage.tsx:98,108` — смена месяца через день 1 с сохранением конвенции `:51`; тест 31.01 → февраль, 31.03 → февраль.

Раскатка: resource (profk, 105) → frontend (обе бренд-сборки `VITE_BRAND`). Core-четвёрка не менялась, alembic head прежний — не пересобирать. Хвост: порция TEST-068 (`components/materials`), floors в `vitest.config.ts:60` подтянуть.

## Волна 2 — security + non-root resource (~12–15 ч)

**PR-2a `AUD7-SEC-04`** (resource, 2–3 ч). `services/exports.py:78,98,108` — нейтрализация `= + - @ \t \r` в начале ячейки (CSV — префикс `'`, XLSX — строковый тип); тест проверяет содержимое файла: `=1+1` в O2 не формула (`data_type != 'f'`), CSV без ведущего `=`.

**PR-2b `AUD7-ENG-08`** (resource, 1.5 ч) — в ту же раскатку resource. `resource-accounting/backend/Dockerfile:1,15` — `USER`; проверить права на volume/tmp; compose (`docker-compose.yml:594,627`, `docker-compose.profk.yml:192,201`) без переопределений. Smoke после `up`: запись в БД и экспорт работают.

**PR-2c `AUD7-SEC-05`** (api, 3–4 ч). `uk_management_bot/api/auth/service.py:275,289,297` — HGETALL/decrement/DELETE одним Lua-скриптом (проверка + потребление атомарно); `:415` reuse detection не трогать. Тест на Redis-double: два верных запроса → один успех; четыре неверных → счётчик −4. Перед раскаткой убедиться, что `EVAL` доступен на прод-Redis.

**PR-2d `AUD7-SEC-02`** (access-api, 2–3 ч). `access_control/api/ws_security.py:119` — предикат `not blocked and not deleted and deleted_at is None`; вызывать ДО подписки (`:175`) и в watcher (`:231`). Тест: deleted и approved+deleted_at → отказ до accept (= HTTP 403 по wire-протоколу).

**Вне кода:** `PENT-F13` — заявка регистратору на CAA + DNSSEC для обоих доменов; проверять снаружи раздельно (CAA и DS).

Раскатка: resource (2a+2b) → core-четвёрка (2c+2d, один ребилд). После `up access-api` проверить, что живые операторы охраны переподключились.

## Волна 3 — достоверность CI и зависимости (~12–15 ч, прод почти не трогает)

**PR-3a `AUD7-ENG-01` → `AUD7-DEP-01`** (1.5 + 2 ч, ENG-01 первым коммитом). `frontend/scripts/audit-gate.mjs:30-45` — отчёт валиден только при наличии `metadata.vulnerabilities`; `{error}`/`{}` → exit 1; фикстура-тест с `{error}`. Затем `npm audit fix`/bump (vitest ≥ 4.1.11, baseline-browser-mapping, js-yaml и остальные); lint, тесты, обе бренд-сборки; для остатков — записанное обоснование. Решить явно: dev-дерево остаётся вне блокирующего гейта (`--omit=dev` в `audit-gate.mjs:31`) — так по дизайну, зафиксировать в записи.

**PR-3b `AUD7-ENG-02` + `AUD7-ENG-04`** (1 + 2 ч). `tests/e2e/package.json:15` — devDeps `typescript`, `@types/node`, скрипт `typecheck`; `.github/workflows/e2e.yml:43` — вызывать его. `ci.yml:121,135` (bandit), `:201,213` (pip-audit), images-build (`:1113+`) — добавить `payment_control`.

**PR-3c `AUD7-ENG-03`** (4–5 ч, отдельно — шумный diff). Lock-файлы для `media_service/requirements.txt`, `resource-accounting/backend/pyproject.toml:7`, `payment_control/requirements.txt` (pip-compile или uv.lock); Dockerfile'ы и `ci.yml:278` ставят из lock. CI зелёный на обоих наборах.

Раскатка: frontend (lock из 3a). Образы media/resource/payment после 3c пересобрать в волне 4/5 вместе с кодовыми изменениями (тот же код, новые слои).

## Волна 4 — сессии, WS, Group Intake (~13–16 ч)

**PR-4a `AUD7-CODE-01` + `AUD7-CODE-02`** (frontend, 3 + 2 ч). CODE-01: `stores/authStore.ts:55` — bootstrap через coordinator `api/client.ts:133`; тест «два параллельных bootstrap → один POST /refresh». CODE-02: `hooks/useWebSocket.ts:90,109,117` — счётчик поколения, поздний `onclose` не ставит reconnect после cleanup и при смене endpoint; тест с отложенным close (мок `:26` дополнить очередью событий).

**PR-4b `AUD7-CODE-03` + `AUD7-CODE-04`** (бот + миграция, 6–8 + 1 ч). CODE-04: `services/group_intake/pending.py:142-144` — `SET NX EX` + INCR (или Lua), TTL гарантирован; тест «ошибка EXPIRE → TTL есть». CODE-03: CAS в `handlers/group_intake.py:951,968,1016` (GETDEL/WATCH до создания заявки), `pending.py:85` не возвращать stale draft; **миграция `alembic/versions/0019_*`** — partial unique index `requests(source_chat_id, source_message_id) WHERE source_message_id IS NOT NULL`, `UniqueConstraint` в `models/request.py:62`; `alembic check` в CI. **До мержа**: SELECT дублей на обоих продах, при дублях — ручная чистка, иначе миграция упадёт. Тест «двойное нажатие → одна заявка».

Раскатка: frontend → core-четвёрка с `migrate` (0019) на обоих; на profk дополнительно `--profile group-intake build/up group-intake-bot`. Хвост: порция TEST-068 (`twa/pages`).

## Волна 5 — media (~9–11 ч)

**PR-5a `AUD7-ARCH-03`** (4–5 ч). `media_service/app/services/telegram_client.py:185-223` — один общий deadline (`asyncio.timeout`) вокруг ожидания semaphore + цикла ретраев; попытка не стартует, если остаток бюджета меньше её таймаута; настройка в `core/config.py` (дефолт < 30 с). Тест худшего случая: три read-timeout подряд → завершение в бюджете. Правка записи BUG-189 в `docs/bugs-2026-09-09.md:70`.

**PR-5b `AUD7-ARCH-01`** (5–6 ч). `services/media_search.py:25,94,97` — sync SQL через `run_in_threadpool` или async engine; `services/media_storage.py:63,596,75` — сессия закрывается до ожидания Telegram, открывается заново после. Тесты на порядок открытия/закрытия.

Раскатка: media-service на обоих одним ребилдом после обоих merge. Контрольная точка 48 ч: в логах media нет ответов дольше 30 с, нет роста `Unclosed client session`.

## Волна 6 — документация запуска и эксплуатация (~10–12 ч + стенд)

**PR-6a `AUD7-ENG-05` + `AUD7-ENG-06`** (2 + 3 ч, одна вычитка первого запуска). ENG-05: `Makefile:105` → сервис `migrate` через Doppler, `README.md:72`, `docs/ops/RUNBOOK.md:73,111`, `docs/tech/ARCHITECTURE.md:264` (refresh 7 дней как в `auth/service.py:98`). ENG-06: `.env.example` — все обязательные `RESOURCE_*`, `ACCESS_*`, `DEPLOY_UID/GID` с безопасными dev-значениями либо dev-overlay без `:?`; README `:51/:55` — экспорт UID/GID до первого `up`; CI-шаг «`docker compose config` с example-env» как гейт. Прод не трогается.

**PR-6b `AUD7-ENG-07`** (4 ч + restore-стенд). `docs/ops/` — реестр бэкапов (5 БД profk, 4 на 105, расписания, retention, RPO/RTO, владелец) по фактам кросс-бэкапа 2026-09-02/06; списание `scripts/backup-db.sh` и правка `scripts/README.md:36`, `scripts/crontab.production`; restore-репетиция всех БД в изолированном контейнере с отчётом (не `pg_restore -l`). Без записи на прод.

## Волна 7 — чистка и долг размещения (~9 ч)

**PR-7a `AUD7-SIMP-01` + `AUD7-SIMP-02`** (1 + 1 ч). Удалить 9 файлов `uk_management_bot/config/locales/*` (all_locales, *.backup_*) + гейт «в locales только ru/uz»; удалить 6 символов (`states/request_assignment.py:8`, `states/shift_management.py:99,122`, `keyboards/user_verification.py:335,437,447`) с grep-проверкой потребителей.

**PR-7b `AUD7-SIMP-03`** (4 ч) → **PR-7c `AUD7-ARCH-02`** (3 ч), последовательно (оба трогают `services/work_reports/sync.py`). SIMP-03: patch targets в тестах переносятся на реальные модули, `_svc()` из `sync.py:135`, `autopublish.py:99`, `reconcile.py:96` убирается, фасад `work_report_service.py:18` остаётся без обратной связи. ARCH-02: три импорта (`services/residents/core.py:31`, `work_reports/sync.py:14`, `inbound_alert.py:16`) переносятся в services + AST-гейт «services не импортируют api.*».

Раскатка: core-четвёрка одним ребилдом после 7c. Хвост: последняя порция TEST-068 (`components/addresses`), floors к 80 % или зафиксировать честный остаток.

## Решения владельца (вне кодовых волн)

- **AUD7-DOC-01 → AUD7-SEC-03.** Выбрать каноническую версию RBAC-документов (ветка unified-rbac `d1aeb281` или локальные `.local-2026-09-12`), закоммитить в `docs/tech/`; затем решение об окне отзыва resource-сессии (сейчас cookie 12 ч, ticket 60 с) — только после него SEC-03 становится actionable.
- **AUD3-07, AUD5-CODE-10, AUD5-ARCH-4, ARCH-06** — ратчеты стоят, режим «при касании»; переоткрывать только при намерении разносить сервисы.
- **DB-049** — JSONB+GIN для ролей только при появлении запроса, которому нужен индекс.
- **SEC-115** — остаток внешний (enforcement на стороне InfraSafe).
- **AUD5-JUNK-5** — пофайловое решение по локальным venv/PNG, не удалять автоматически.

## Верификация

- Каждый PR: RED-тест воспроизводит дефект по сценарию из отчёта 2026-09-15 (готовые пробы в таблице «Все 34 открытые задачи»), GREEN после фикса, `make test-ci` перед мержем, CI 13/13.
- Каждая волна: раскатка по рунбуку, прод-проверка по логам (`docker logs` соответствующего контейнера: нет 5xx/422, нужный сценарий отдаёт 200), тег `profk-YYYY-MM-DD` / `infrasafe-YYYY-MM-DD`, обновление памяти о состоянии прода.
- Бэклог: после каждой волны `python3 -B scripts/backlog_manifest.py --check` — число открытых уменьшается ровно на закрытые пункты; финал — 0 actionable, остаются только decision/deferred/no-pr.
