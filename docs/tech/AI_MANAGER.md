# ИИ-менеджер заявок (режим `mode="ai"` автоменеджера)

> _Последнее редактирование: 2026-10-28_ · фазы 0–2 (общий LLM-клиент, триаж, SLA-лестница). Мониторинг отключений — следующий PR.

## Идея

Третий режим диспетчеризации рядом с «без назначения» (`enabled=false`) и «автоназначение» (`mode="rule"`). Подход «тонкий ИИ»: модель **понимает свободный текст** (RU/UZ), решения **принимают правила**. Выбор исполнителя остаётся за rule-engine (`services/auto_manager/rule_engine.py`): смена + специализация + нагрузка.

Фильтр «что LLM, что конфиг»: LLM только там, где вход — свободный текст и правила вырождаются в бесконечный список ключевых слов. Три точки: (1) категория/срочность/дубль по тексту заявки, (2) непонятная заявка → вопрос жителю на его языке, (3) релевантность новости комплексу (фаза 3). Всё остальное — конфиг, шаблоны, таймеры.

## Выключатели (три уровня)

| Уровень | Где | Эффект при выключении |
|---|---|---|
| Деплой: `AI_MANAGER_ENABLED` (dark по умолчанию) | `config/settings.py` | API-схема не принимает `mode="ai"`, бот показывает «ИИ (скоро)», `ai_available=false` в `GET /api/v2/auto-manager-config`. Флаг без `ANTHROPIC_API_KEY` → warning и принудительное `false`, **не падение** |
| Рантайм: `auto_manager_config.data.mode` = `rule \| ai` | бот («Автоменеджер» → кнопка режима), дашборд (карточка на «Сменах») | `dispatch` идёт прежним путём; пакет `services/ai_manager` не импортируется |
| Вызов: деградация + предохранитель | `services/ai_manager/breaker.py` (Redis `ai:breaker:*`) | Любой сбой LLM / низкая уверенность → rule-путь; 3 сбоя подряд → 10 мин без LLM, одно уведомление менеджеру |

Состояние ИИ **не хранится** отдельно: решения — строки `audit_logs` (`ai_triage_applied`, `ai_triage_failed`), миграций нет.

## Конвейер триажа (`services/dispatch.py` → `services/ai_manager/apply.py`)

```
создание заявки → auto_dispatch_new_request_{sync,async}
  → enabled? → mode == ai? (AI_MANAGER_ENABLED && cfg.mode)
  → apply_triage_sync(request_number, cfg.ai)
       контекст: текст, язык жителя, открытые заявки адреса (7 дн, ≤5)
       detect_emergency(text)            — правило, всегда (газ/затоп/лифт/дым…) → critical
       llm_payload_sync(...)             — Sonnet 5.5, effort low, structured output
       parse_llm_triage(...)             — словари/диапазоны в Python; confidence < порога → None
       применение (принципал system_actor="ai_manager"):
         дубль        → уведомление менеджеру (заявку не трогаем)
         непонятно    → CLARIFY_REQUEST + вопрос жителю (clarification_text) → dispatch СТОП («clarified»)
         категория    → MANAGER_CHANGE_CATEGORY → spec пересчитывается
         срочность    → UPDATE requests.urgency (max: текущая, аварийная, LLM) — не переход
         маркер       → audit ai_triage_applied (после успешных команд; идемпотентность)
       сбой на любом шаге → audit ai_triage_failed, возврат в rule-путь
  → pick_assignee_id(category) → SYSTEM_DISPATCH_ASSIGN / ASSIGN_GROUP (как раньше)
```

Границы полномочий — в коде, не в промпте: `SYSTEM_CAPABILITIES["ai_manager"]` в `utils/request_workflow/guards.py` = `{CLARIFY_REQUEST, MANAGER_CHANGE_CATEGORY, SYSTEM_DISPATCH_ASSIGN, ASSIGN_GROUP}`. Отмена, закрытие, подтверждение, возврат в работу — не выдаются; «Инженерный разбор» триаж не трогает.

## Конфиг

`auto_manager_config.data.ai` (вложенный merge поверх дефолтов, валидация в `services/auto_manager/config.py::_validate_ai`):

```json
{"min_confidence": 0.7, "clarify_enabled": true, "dedup_enabled": true}
```

Env: `AI_MANAGER_MODEL=claude-sonnet-5-5`, `AI_MANAGER_EFFORT=low`, `AI_MANAGER_LLM_TIMEOUT=8`, общий `ANTHROPIC_API_KEY` с Group Intake (Doppler). Haiku 5.5 — переключение через `AI_MANAGER_MODEL`, промпт и схема те же.

## SLA-лестница (`services/ai_manager/sla.py`, без LLM)

Job `ai_sla_tick` каждые 10 мин — регистрируется только при `AI_MANAGER_ENABLED`, внутри пуст при `mode != "ai"`. Один следующий шаг на заявку за тик; при простое тика лестница **не** догоняется целиком.

| Трек | Условие | Якорь фазы | Шаги |
|---|---|---|---|
| `executor` | «В работе» с исполнителем дольше `sla.in_progress_max[urgency]` ч | `assigned_at` | DM исполнителю → staff-группа (`monitored_groups.kind=staff`) → менеджеры → `SYSTEM_REASSIGN` дежурному (кроме текущего; нет кандидата → менеджер) — смещения `sla.ladder` в часах от момента просрочки |
| `clarification` | «Уточнение» дольше `clarification_max` ч | `updated_at` | напоминание жителю (его язык) → менеджеры (ещё через столько же) |
| `executed` | «Исполнено» без проверки дольше `executed_unconfirmed_max` ч | `executed_at` | менеджеры |
| `completed` | «Выполнена» без принятия дольше `completed_unaccepted_days` дн | `completed_at` | `MANAGER_FORCE_ACCEPT` + DM жителю |
| `critical_unassigned` | критическая «Новая» без исполнителя дольше `critical_unassigned_minutes` | `created_at` | менеджеры |

`0` в любом нормативе выключает трек/ступень. Состояние — строки `audit_logs` `ai_sla_step` с `{track, step, step_index, status_version, phase_started_at, result}`; шаг относится к текущей фазе только при совпадении `(track, status_version, phase_started_at)` — переназначение, возврат в работу, смена статуса начинают лестницу заново. Чтение — один запрос по кандидатам за 30 дней (`# ponytail`: отдельная таблица, если тик > 1 с).

Каналы — `services/ai_manager/channels.py` (DM / staff-группа / менеджеры / группа жителей); SMS и звонок добавляются там как новый `kind`. Шаблоны — `ai_manager.sla.*` в локалях бота. Настройки — блок `sla` на карточке автоменеджера дашборда (только при `ai_available`).

Выключение режима (бот или дашборд, `ai → rule`): менеджерам одно сообщение с числом открытых заявок, у которых были шаги лестницы за 30 дней (`services/ai_manager/switch_off.py`).

Публичный статус (`public_status.py`): для **критических** заявок из группы жителей (`source_chat_id` = активная residents-группа) при назначении/выполнении — шаблон RU+UZ без ФИО и квартиры в тот же чат; хук в диспетчерах `workflow_notifications`.

Новые действия workflow: `SYSTEM_REASSIGN` («В работе» → «В работе», system-only, capability только `ai_manager`); `MANAGER_FORCE_ACCEPT` открыт системному актору `ai_manager`.

## Общий LLM-клиент (`services/llm/client.py`)

Один цикл для Group Intake и ИИ-менеджера: structured output (`output_config.format`), один повтор транзиентного сбоя (jitter / `retry-after` на 429), общий дедлайн `attempts × timeout`, гейт `retry_allowed`, `None` на любой отказ. Модуль импортирует только `settings` + `anthropic` — его тянет и отдельный процесс Group Intake. Схемы — плоские (без `enum/minimum/maximum/maxLength`): словари и диапазоны проверяет вызывающий.

## Тесты

- `tests/services/test_llm_client.py`, `test_ai_triage.py`, `test_ai_breaker.py`, `test_ai_apply.py` (sqlite, реальный `run_command_sync`), `test_dispatch.py` (golden: rule-режим не трогает пакет), `test_ai_sla.py` (лестница по фазам), `test_ai_switch_off.py`, `test_ai_public_status.py`.
- `uk_management_bot/tests/test_auto_manager_ai_config.py`, `test_request_workflow.py` (capability `ai_manager`), `test_auto_manager_handler.py` (переключатель), `test_settings.py` (форс-выключение без ключа).
- `tests/api/test_auto_manager_config.py` (`ai_available`, `mode="ai"` под флагом).
- Фронт: `AutoManagerCard.test.tsx`.

## Включение на площадке

1. Doppler: `AI_MANAGER_ENABLED=true` сервисам `app` и `api` (ключ `ANTHROPIC_API_KEY` уже есть у Group Intake).
2. Деплой по `uk-deploy` (миграций нет).
3. Менеджер переключает режим в боте или на дашборде. Выключение — обратный тап; состояния «в полёте» нет.
