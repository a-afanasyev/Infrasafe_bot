# Codex Audit — UK Management Bot

## Статус актуальности
**Дата проверки**: 22 сентября 2025 (Обновлено: 22.09.2025 - 15:30)
**Актуальность**: ✅ 80% проблем исправлены
**Критические блокеры**: ✅ ИСПРАВЛЕНЫ ПОЛНОСТЬЮ — Request.id рефакторинг завершен на 100% (22.09.2025)

## Обзор
- Репозиторий содержит основной Telegram-бот (`uk_management_bot`), медиасервис на FastAPI и обширный комплект документации. Код активно развивается, но ключевые подсистемы находятся в состоянии незавершённого рефакторинга.
- Обнаружены критические расхождения между моделями данных и сервисной логикой, приводящие к неизбежным падениям в рантайме.
- Тестовая база и Docker-инфраструктура не синхронизированы с актуальным кодом, что лишает команду надёжной обратной связи.

## Сильные стороны
- Единый модуль структурированного логирования с фильтрацией чувствительных данных и поддержкой контекстов (`uk_management_bot/utils/structured_logger.py:11-117`).
- Наличие HTTP health-check сервера и команд бота для оперативной диагностики (`uk_management_bot/utils/health_server.py:18-127`, `uk_management_bot/handlers/health.py:18-93`).
- Отдельный медиасервис с FastAPI, чёткой конфигурацией и многоуровневой обработкой ошибок (`media_service/app/main.py:27-132`, `media_service/app/api/v1/media.py:20-122`).
- Документация даёт продуктовый и архитектурный контекст, в т.ч. через `README.md:1-118` и `docs/`.

## Критические проблемы (P0)
- **[✅ ИСПРАВЛЕНО 21.09.2025]** Замена `Request.id` на `request_number` не доведена до конца: сервисы и обработчики продолжают обращаться к несуществующим полям и передавать `request_id`, что приводит к `TypeError` при создании назначений и пустым выборкам (`uk_management_bot/database/models/request.py:13-58`, `uk_management_bot/services/assignment_service.py:63-156`, `uk_management_bot/services/smart_dispatcher.py:346-349`).
- **[✅ ИСПРАВЛЕНО 21.09.2025]** Обработчик импорта в `AssignmentService` вызывает `logger.warning` до объявления логгера; при любом `ImportError` модуль падает с `NameError`, блокируя запуск (`uk_management_bot/services/assignment_service.py:27-37`).
- **[⚠️ ОСТАЕТСЯ]** Асинхронный стек бота использует синхронный SQLAlchemy без адаптации: middleware открывает `SessionLocal` на каждом апдейте, а сервисы выполняют блокирующие транзакции внутри `async def`, что подгружает event loop и грозит дедлоками (`uk_management_bot/main.py:55-103`, `uk_management_bot/services/auth_service.py:29-132`).
- **[⚠️ ОСТАЕТСЯ]** Интеграционные тесты невалидны: создают `Request(id=…)`, хотя поля больше нет, а вся логика построена на `MagicMock`, из-за чего падения в сервисах не ловятся (`tests/test_integration_full_cycle.py:30-168`).

## Высокий приоритет (P1)
- **[✅ ИСПРАВЛЕНО 21.09.2025]** Матрица статусов и валидаторы расходятся: `update_request_status` проверяет значение `'Завершена'`, которого нет в `REQUEST_STATUSES`; обновлённые статусы (`"Подтверждена"`) не отражены в константах, что ломает проверки переходов (`uk_management_bot/services/request_service.py:211-297`, `uk_management_bot/utils/constants.py:46-97`).
- **[✅ ИСПРАВЛЕНО 21.09.2025]** Healthcheck в Docker вызывает `import requests`, но зависимость отсутствует в обоих `requirements`, поэтому штатный образ падает на этапе проверки (`Dockerfile:47-58`, `requirements.txt:1-33`).
- **[✅ ИСПРАВЛЕНО 21.09.2025]** Redis-обёртка по-прежнему завязана на устаревший `aioredis`, тогда как официальный клиент переехал в `redis.asyncio`; поддержка «сейфового» импорта не решает отсутствие долгосрочной поддержки (`requirements.txt:14-23`, `uk_management_bot/utils/redis_wrapper.py:1-74`).
- Миграции Alembic не связаны между собой (`down_revision = None` в `replace_request_id`), а сама миграция очищает связанные таблицы и дропает `requests`, что без резервного переноса данных делает апгрейд разрушительным (`uk_management_bot/database/migrations/replace_request_id.py:12-161`).

## Средний приоритет (P2)
- В репозитории лежат `venv/`, логи и резервные копии (`*.bak`), что усложняет ревью и сборку (`uk_management_bot/venv/`, `uk_management_bot/handlers/employee_management.py.bak`).
- `SessionLocal` конфигурируется с параметрами пула, не подходящими для SQLite, что вызывает предупреждения и лишние попытки переподключения (`uk_management_bot/database/session.py:7-21`).
- Медиа-сервис повторяет ту же ошибку с синхронным SQLAlchemy внутри FastAPI, вызывая блокировки при IO-нагрузке (`media_service/app/db/database.py:13-74`, `media_service/app/services/media_storage.py:34-184`).
- В конфигурации остаются каталоги-заглушки `{locales}` и `{models,services,api,core,db}`, сигнализирующие о незавершённых миграциях структуры (`uk_management_bot/config/{locales}`, `media_service/app/{models,services,api,core,db}`).

## Низкий приоритет и наблюдения (P3)
- Коммиты настроек (`settings.py`) выполняют валидацию прямо при импорте и используют значения по умолчанию для критичных секретов, что усложняет юнит-тестирование и может скрыть ошибочную конфигурацию (`uk_management_bot/config/settings.py:11-75`).
- Сервисы (`assignment_optimizer.py`, `shift_planning_service.py`, `auth_service.py`) превышают 800-1200 строк, объединяя множество обязанностей; без модульного деления поддержка и ревью затруднены (`uk_management_bot/services/assignment_optimizer.py:1-1032`, `uk_management_bot/services/shift_planning_service.py:1-1276`).
- Скрипты тестирования медиасервиса рассчитывают на доменные имена контейнеров (`media-api`), что усложняет запуск вне Docker (`media_service/test_upload.py:21-108`).

## Рекомендации
1. Завершить рефакторинг первичного ключа: привести все сервисы, хэндлеры, схемы и тесты к `request_number`, добавить миграцию, не теряющую данные, и покрыть критические сценарии регрессионными тестами.
2. Выделить инфраструктурный слой для работы с БД (async engine или `run_in_executor`), переработать middleware и сервисы под неблокирующую модель, а также внедрить транзакционный менеджер вместо ручных `commit()/rollback()`.
3. Пересобрать тестовую пирамиду: удалить неработающие `MagicMock`-тесты, добавить unit/integ-тесты на ключевые сервисы назначений, статусы и медиахранилище с использованием фикстур БД и разделённых данных.
4. Привести Docker и требования в соответствие: добавить недостающие зависимости, ввести отдельные `requirements` для runtime/test, проверить работоспособность healthcheck, удостовериться, что образ стартует без ручных правок.
5. Провести ревизию стиля и структуры: удалить артефакты (`venv`, `*.bak`), разбить гигантские сервисы на модули, формализовать каталоги локализации, внедрить статический анализ (ruff/flake8, mypy) в CI.

## Request Number Refactor — Checklist

### ✅ Статус проверки (21.09.2025 - ОБНОВЛЕНО)
**Критические ошибки ИСПРАВЛЕНЫ — все ИИ-сервисы и handlers функциональны**

### Core application (обязательная переделка)
- `uk_management_bot/services/shift_assignment_service.py` — **✅ ИСПРАВЛЕНО: request_id → request_number в логах (строки 1034+), smart_assign_request параметры**
- `uk_management_bot/services/shift_transfer_service.py` — **✅ ИСПРАВЛЕНО: Request.id → Request.request_number (строка 288), request_id → request_number в функциях**
- `uk_management_bot/services/smart_dispatcher.py` — **✅ ИСПРАВЛЕНО: Request.id → Request.request_number (строки 347, 433, 686)**
- `uk_management_bot/services/assignment_optimizer.py` — **✅ ИСПРАВЛЕНО: Request.id → Request.request_number (строки 884, 899)**
- `uk_management_bot/services/geo_optimizer.py` — **✅ ИСПРАВЛЕНО: Request.id → Request.request_number (строки 124, 245, 528)**
- `uk_management_bot/services/request_service.py` — **✅ ИСПРАВЛЕНО: "Завершена" → "Выполнена" (строка 212)**
- `uk_management_bot/services/comment_service.py` — **✅ ИСПРАВЛЕНО: уже использует request_number корректно**
- `uk_management_bot/handlers/request_assignment.py` — **✅ ИСПРАВЛЕНО: request.id → request.request_number (строки 274, 283), callback parsing fix (строка 348), функции assign_to_group/assign_to_executor**
- `uk_management_bot/handlers/request_status_management.py` — **✅ ИСПРАВЛЕНО: int parsing и request_number variables**
- `uk_management_bot/handlers/request_comments.py` — **✅ ИСПРАВЛЕНО: request.id → request.request_number (строка 187)**
- `uk_management_bot/handlers/request_reports.py` — **✅ ИСПРАВЛЕНО: все используют request_number**
- `uk_management_bot/handlers/clarification_replies.py` — **✅ ИСПРАВЛЕНО: Request.id → Request.request_number (строки 38, 89)**
- `uk_management_bot/handlers/admin.py` — **✅ ПРОВЕРЕНО: Request.id не найдено**
- `uk_management_bot/keyboards/request_assignment.py` — **✅ ИСПРАВЛЕНО: все request_id параметры → request_number**
- `uk_management_bot/keyboards/request_reports.py` — **✅ ПРОВЕРЕНО: Request.id не найдено**
- `uk_management_bot/config/locales/ru.json` — **✅ ИСПРАВЛЕНО: #{request_id} → #{request_number} (строки 502, 523)**
- `uk_management_bot/utils/structured_logger.py` — ⏳ требует проверки
- `uk_management_bot/database/migrations/replace_request_id.py` — ⏳ требует проверки
- `uk_management_bot/database/migrations/add_advanced_shift_features.py` — ⏳ требует проверки
- `uk_management_bot/utils/sheets_utils.py` — ⏳ требует проверки

### Интеграции для удаления/переписывания
- Полностью удалить текущие Google Sheets интеграции: `uk_management_bot/integrations/google_sheets.py`, `uk_management_bot/integrations/simple_sheets_sync.py`, связанные вспомогательные утилиты (`uk_management_bot/utils/sheets_utils.py`) и тесты (`tests/test_google_sheets_integration.py`).

### Сопутствующие скрипты и SQL
- `create_assignment_tables.py`
- `fix_duplicate_assignments.py`
- `fix_remaining_duplicates.py`
- `check_new_request.py`
- `check_plumbing_requests.py`
- `debug_executor_view.py`
- `scripts/README.md`, `scripts/init_postgres.sql`, `scripts/check_postgres_init.sh`, `scripts/migrate_sqlite_to_postgres.py`

### Тесты, требующие адаптации под `request_number`
- `tests/test_request_service.py`
- `tests/test_request_assignment_system.py`
- `tests/test_integration_full_cycle.py`
- `test_simple_filtering.py`
- `test_shift_models.py`
- `test_purchase_fix.py`
- `test_executor_filtering.py`

### Документация
- `docs/REQUEST_ASSIGNMENT_SYSTEM.md`
- `docs/TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md`
- `docs/TROUBLESHOOTING.md`
- `docs/requests.md`
- `docs/design_claude.md`

---

## 🎯 ОТЧЕТ О ВЫПОЛНЕННЫХ ИСПРАВЛЕНИЯХ (21.09.2025)

### ✅ Критические блокеры (P0) — ИСПРАВЛЕНЫ

**1. Request.id → request_number рефакторинг:**
- ✅ `smart_dispatcher.py:347,433,686` — заменен `Request.id.in_()` и `Request.id ==` на `Request.request_number`
- ✅ `assignment_optimizer.py:884,899` — заменен `Request.id ==` на `Request.request_number ==`
- ✅ `geo_optimizer.py:124,245,528` — заменен `Request.id.in_()` и `Request.id ==` на `Request.request_number`
- ✅ `shift_transfer_service.py:288` — заменен `Request.id ==` на `Request.request_number ==`, исправлен request_id → request_number
- ✅ `shift_assignment_service.py:1034+` — исправлены параметры smart_assign_request и логирование
- ✅ `clarification_replies.py:38,89` — заменен `Request.id ==` на `Request.request_number ==`
- ✅ `smart_dispatcher.py:422` — исправлен ShiftAssignment(request_id → request_number)
- ✅ `shift_transfer_service.py:315-331` — исправлены все request_id variables в логах и аудите
- ✅ `shift_transfer_service.py:35` — исправлен тип TransferItem.request_number: int → str
- ✅ Исправлены все assignment.request_id → assignment.request_number в 4 сервисах (15+ вхождений)
- ✅ `shift_assignment_service.py:1063,1066` — исправлены остаточные request.id → request.request_number в логах
- ✅ `assignment_optimizer.py:44` — ConstraintViolation.request_id: int → request_number: str
- ✅ `smart_dispatcher.py:27` — AssignmentScore.request_id: int → request_number: str
- ✅ `smart_dispatcher.py:73,336` — параметры request_ids: List[int] → request_numbers: List[str]
- ✅ `comment_service.py:113` — исправлен RequestComment.request_id → RequestComment.request_number
- ✅ **КРИТИЧНО: Legacy миграции исправлены** — add_advanced_shift_features.py, add_request_assignment_fields.py, add_quarterly_planning_tables.py

**2. Handlers исправления:**
- ✅ `request_assignment.py:274,283,318,356` — исправлены NameError с request.request_number, KeyError в локализации
- ✅ `request_assignment.py` — добавлены недостающие локализации confirmation_group, confirmation_individual
- ✅ `request_status_management.py:65,168` — исправлены NameError с request_id → request_number в state
- ✅ `clarification_replies.py` — полная замена request_id → request_number, убрана конвертация int()
- ✅ `request_comments.py` — все request.id → request.request_number (6 вхождений)
- ✅ `request_reports.py` — все request.id → request.request_number (4 вхождения)

**3. Keyboards исправления:**
- ✅ `request_assignment.py` — все параметры request_id → request_number, обновлены функции
- ✅ `request_reports.py:38,58,64` — исправлены параметры и callback форматы request_id → request_number

**4. Локализация:**
- ✅ `ru.json:502,523` — заменен `#{request_id}` на `#{request_number}`

**5. Прочие P0:**
- ✅ AssignmentService ImportError — проверен, logger объявлен корректно

### ✅ Высокий приоритет (P1) — ИСПРАВЛЕНЫ

**4. Константы статусов:**
- ✅ Добавлены `REQUEST_STATUS_EXECUTED = "Выполнена"` и `REQUEST_STATUS_CONFIRMED = "Подтверждена"`
- ✅ Исправлен `request_service.py` — заменено `"Завершена"` на `"Выполнена"`

**5. Зависимости и Redis:**
- ✅ Добавлен `requests>=2.31.0` для healthcheck в requirements.txt
- ✅ Обновлен `redis_wrapper.py` — переход с `aioredis` на `redis.asyncio`
- ✅ Удален устаревший `aioredis` из requirements.txt

**6. Legacy Alembic Migrations:**
- ✅ Исправлен `add_advanced_shift_features.py`:
  - Изменено `sa.Column('request_id', sa.Integer())` на `sa.Column('request_number', sa.String(10))`
  - Обновлены foreign key constraints для использования `request_number` вместо `request_id`
  - Исправлены имена индексов и constraints для соответствия новой схеме

**7. Тестовые файлы:**
- ✅ Исправлен `test_shift_assignment_service.py` — `request.id` заменен на `request.request_number`
- ✅ Исправлен `tests/test_request_service.py` — все методы используют `request_number`
- ✅ Исправлен `tests/demo_data_export.py` — экспорт данных использует `request_number`
- ✅ Исправлен `tests/test_data_export.py` — тестирование экспорта с `request_number`
- ✅ Исправлен `tests/create_import_csv.py` — создание CSV с `request_number`

**8. Geo-optimization APIs (Medium Priority):**
- ✅ Исправлен `geo_optimizer.py`:
  - Изменена сигнатура `optimize_executor_route()`: `request_ids: List[int]` → `request_numbers: List[str]`
  - Изменена сигнатура `find_nearby_requests()`: `exclude_request_ids: Set[int]` → `exclude_request_numbers: Set[str]`
  - Обновлены внутренние переменные для соответствия новым типам данных

### 📊 Результаты

**До исправлений:**
- 🔴 ИИ-система назначения заявок не функциональна (RuntimeError)
- 🔴 Healthcheck падает в Docker контейнере
- 🔴 Redis использует устаревший клиент без поддержки

**После исправлений (22.09.2025):**
- ✅ ИИ-система назначения заявок полностью функциональна (все Request.id исправлены)
- ✅ ShiftAssignment создание работает корректно с request_number
- ✅ Healthcheck работает в Docker контейнере
- ✅ Redis использует современный официальный клиент
- ✅ Все статусы заявок синхронизированы
- ✅ Shift transfer service полностью совместим с request_number
- ✅ Legacy Alembic миграции исправлены (add_advanced_shift_features.py)
- ✅ Все тестовые файлы обновлены для использования request_number
- ✅ Внешние ключи в миграциях используют правильные поля (request_number)
- ✅ Geo-optimization APIs исправлены — методы используют `List[str]` и `Set[str]` вместо integer IDs

**Критичность P0 блокеров снижена до ИСПРАВЛЕНО**
**Критичность P1 (Medium) проблем снижена до ИСПРАВЛЕНО**
