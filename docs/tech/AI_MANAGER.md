# ИИ-менеджер заявок (режим `mode="ai"` автоменеджера)

> _Последнее редактирование: 2026-10-28_ · фазы 0–1 (общий LLM-клиент, триаж). SLA-лестница и мониторинг отключений — следующие PR.

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

## Общий LLM-клиент (`services/llm/client.py`)

Один цикл для Group Intake и ИИ-менеджера: structured output (`output_config.format`), один повтор транзиентного сбоя (jitter / `retry-after` на 429), общий дедлайн `attempts × timeout`, гейт `retry_allowed`, `None` на любой отказ. Модуль импортирует только `settings` + `anthropic` — его тянет и отдельный процесс Group Intake. Схемы — плоские (без `enum/minimum/maximum/maxLength`): словари и диапазоны проверяет вызывающий.

## Тесты

- `tests/services/test_llm_client.py`, `test_ai_triage.py`, `test_ai_breaker.py`, `test_ai_apply.py` (sqlite, реальный `run_command_sync`), `test_dispatch.py` (golden: rule-режим не трогает пакет).
- `uk_management_bot/tests/test_auto_manager_ai_config.py`, `test_request_workflow.py` (capability `ai_manager`), `test_auto_manager_handler.py` (переключатель), `test_settings.py` (форс-выключение без ключа).
- `tests/api/test_auto_manager_config.py` (`ai_available`, `mode="ai"` под флагом).
- Фронт: `AutoManagerCard.test.tsx`.

## Включение на площадке

1. Doppler: `AI_MANAGER_ENABLED=true` сервисам `app` и `api` (ключ `ANTHROPIC_API_KEY` уже есть у Group Intake).
2. Деплой по `uk-deploy` (миграций нет).
3. Менеджер переключает режим в боте или на дашборде. Выключение — обратный тап; состояния «в полёте» нет.
