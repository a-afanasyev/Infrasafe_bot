# PR0 — SSOT-кластер #1: preflight и решения

Дата: 2026-06-10. Статус: **preflight выполнен; ВСЕ решения зафиксированы (Р3 подтверждён продуктово 2026-06-10: возврат через менеджера).**
План: `~/.claude/plans/deep-shimmying-torvalds.md`. Выполнено до PR0: HF-0, PR5, PR6 (в проде, PR #47-49).

---

## 1. Prod-preflight (read-only, 2026-06-10)

### 1.1 Состояния (`GROUP BY status, manager_confirmed, is_returned`)

| status | manager_confirmed | is_returned | count |
|---|---|---|---|
| Новая | f | f | 6 |
| Принято | t | f | 2 |
| Отменена | f | f | 1 |

Выводы:
- **Грязных/неоднозначных сочетаний нет** → backfill PR3 на текущих данных тривиален; quarantine-список пуст.
- `Принято + manager_confirmed=true` — Telegram-цикл (confirm → accept) реально используется.
- Заявок в промежуточных состояниях (`В работе`, `Выполнена`, `Исполнено`) на момент снимка нет — cutover-окно при таком профиле почти безрисково.

### 1.2 Реальные переходы (`audit_logs`, action=request_status_changed)

| old | new | actor | count |
|---|---|---|---|
| Выполнена | Выполнена | manager_confirm | 5 |
| Новая | В работе | **NULL** | 3 |
| Исполнено | Принято | applicant_accept | 1 |

Выводы:
- **Flag-only self-edge подтверждён живыми данными** (`Выполнена→Выполнена` + manager_confirmed) — булев guard `is_transition_allowed(old,new)` его не выразит; action-модель обязательна (риск №3 плана — подтверждён).
- **Actor-less переходы существуют** (`Новая→В работе`, actor NULL — автодиспетчер/bypass) → SYSTEM-actions обязательны (риск №5 — подтверждён).
- **audit_logs неполен**: 9 записей на историю, где переходов было больше (2 Принято прошли полный цикл; force-accept/cancel/return не залогированы единым форматом) → рёбра action-table выводим из **объединения** audit + code-inventory (инвентарь write-path в плане, PR2).

### 1.3 Источники

`twa` 3 · `inspector` 4 · `bot` 1 · `infrasafe` 1 — все четыре создающих источника живые; inspector-заявки в обычном жизненном цикле.

### 1.4 Счётчики номеров (после PR5)

`request_number_counters` засеяна, seed == числовой MAX по каждому дню (проверено 2026-06-10). Генерация единая.

---

## 2. Решения

### Р1. Модель состояния — **A (чисто-статусная)** ✅

Канон — линейка статусов `Новая → В работе → (Закуп|Уточнение) → Выполнена → Исполнено → Принято` + `Отменена`. Флаги сворачиваются:
- Telegram-композит `Выполнена + manager_confirmed=true` ⇒ канон `Исполнено`;
- `manager_confirmed`/`is_returned` перестают участвовать в **решениях** (guard'ах/фильтрах) и остаются данными (см. Р6).

Обоснование: фронты/API уже чисто-статусные; outward-проекция ≈ identity; dual-read проще; прод-данные не содержат сочетаний, которые модель A не выразит.

### Р2. Авторизация — **per-action предикат** (не глобальный active_role-vs-role-set) ✅

Для каждого Action в action-table (§3): `roles × active_role × ownership × assignment × active-shift`. SYSTEM-действия — отдельная capability-таблица `system_actor → {Action}` (dispatcher ≠ reconcile). `PrincipalRef{kind, user_id, system_actor, source}` передаётся в `run_command` отдельно от команды; SYSTEM-principal конструируется только внутренними call-site'ами.

### Р3. Семантика возврата — **через менеджера: канон-статус «Возвращена»** ✅ (продуктовое решение 2026-06-10)

`APPLICANT_RETURN: Исполнено → Возвращена` (только owner; payload `{return_reason, return_media?}`; `returned_*` пишутся и как исторические данные). Менеджер — **обязательный шаг** разбора возврата (сохраняет текущий Telegram-flow):
- `MANAGER_RETURN_TO_WORK: Возвращена → В работе` (исполнитель доделывает);
- `MANAGER_FORCE_ACCEPT: Возвращена → Принято` (возврат необоснован);
- `CANCEL: Возвращена → Отменена`.

Последствия нового статуса в каноне:
- **Переходный период (до PR7/contract):** старые читатели (kanban-колонки, кэшированные TWA, InfraSafe-маппинги) статус «Возвращена» не знают → `project_public_state`/`project_infrasafe_state` проецируют его как `Исполнено` до обновления потребителей; после PR7 фронты получают статус из runtime-endpoint.
- **InfraSafe-координация:** новый wire-статус согласовать с InfraSafe (их status-маппинги) ДО contract; до того наружу идёт проекция `Исполнено`.
- Отдельный `MANAGER_RECONFIRM` не нужен: повторное подтверждение после доработки = обычный цикл `Выполнена →[MANAGER_CONFIRM]→ Исполнено`.

### Р4. SYSTEM actor/actions ✅

- `SYSTEM_DISPATCH_ASSIGN` (`Новая → В работе` + assignment) — capability `dispatcher`;
- system-правки reconcile (если потребуются) — отдельная capability `reconcile`;
- `update_request_status` (нерестриктивный) и прямые записи диспетчера — упраздняются в PR2c, всё через `run_command(principal=system)`.

### Р5. Cutover — **stop-the-world app-слоя** ✅ (подтверждено: пилот, ночное окно доступно)

Процедура — план, PR2 cutover-схема п.3 (stop только app; backup; one-off migration-job `--no-deps --entrypoint "python -m alembic"`; postflight-гейт; при провале сервисы остаются стоять). Prep-шаг: зафиксировать фактический список compose-файлов прод-хоста (`docker-compose.yml + docker-compose.media.yml`, media.yml существует только на хосте).

### Р6. Судьба `manager_confirmed` / `is_returned` — **исторические read-only поля** ✅

После contract (PR4): колонки остаются, новые записи их не используют для решений; `manager_confirmed_by/_at`, `returned_*` — аудит-история. Не drop (дёшево хранить, сохраняет историю пилота); не mirror (mirror = вечная двойная запись, источник расхождений). Backfill PR3 НЕ очищает поля → миграция **обратима** (downgrade = ничего не делать со старыми полями).

### Р7. Событийный контракт — durable vs best-effort ✅

- **Durable (outbox, в транзакции):** InfraSafe `request.created` / `request.status_changed`.
- **Best-effort (post-commit intents, потеря при падении процесса допустима):** Redis pub/sub realtime (kanban), Telegram-уведомления пользователям (заявитель/исполнитель/менеджер/канал). Если какое-то Telegram-уведомление станет обязательным — переезд в outbox с воркером, не в intents.
- Webhook несёт **проекции** old/new state (`project_infrasafe_state`); для модели A проекция ≈ identity по status.

### Р8. Идемпотентность — базовый уровень (подтверждение отложенного объёма) ✅

`FOR UPDATE` + state-recheck по `repeat_policy` (`reject` / `no_op_if_same` / `repeatable`) + constraints (`Rating UNIQUE(request_number)`, partial-unique `WHERE status='active'` на RequestAssignment). Processed-commands-таблица — только при появлении клиента с реальным `Idempotency-Key`.

---

## 3. Action-table (черновик PR0 → дорабатывается в PR1)

Канон-статусы: `Новая`, `В работе`, `Закуп`, `Уточнение`, `Выполнена`, `Исполнено`, `Возвращена` *(новый, Р3)*, `Принято`†, `Отменена`† († — терминальные).

| Action | from → to | Авторизация (предикат) | Payload | repeat_policy |
|---|---|---|---|---|
| SYSTEM_DISPATCH_ASSIGN | Новая → В работе | system:dispatcher | `{executor_id?|group}` | no_op_if_same |
| MANAGER_ASSIGN | Новая → В работе | role manager | `{executor_id?|group}` | no_op_if_same |
| EXECUTOR_START? | — | *(нет отдельного ребра: назначение = старт)* | — | — |
| EXECUTOR_PURCHASE | В работе → Закуп | role executor + assigned + active-shift | `{requested_materials}` | reject |
| MANAGER_PURCHASE_DONE | Закуп → В работе | role manager | `{manager_materials_comment?}` | reject |
| CLARIFY_REQUEST | Новая/В работе → Уточнение | role manager | `{question}` | reject |
| CLARIFY_RESOLVED | Уточнение → В работе | role manager | `{}` | reject |
| EXECUTOR_COMPLETE | В работе → Выполнена | role executor + assigned + active-shift | `{completion_report?, completion_media?}` | **repeatable** (после возврата) |
| MANAGER_CONFIRM | Выполнена → Исполнено | role manager | `{confirmation_notes?}` | no_op_if_same |
| MANAGER_RETURN_TO_WORK | Выполнена **или Возвращена** → В работе | role manager | `{reason}` | reject |
| APPLICANT_ACCEPT | Исполнено → Принято | owner **или** одобренный сосед (= HF-0 can_accept) | `{rating: 1..5}` | reject |
| APPLICANT_RETURN | Исполнено → **Возвращена** *(Р3)* | **только owner** (= HF-0 can_return) | `{return_reason, return_media?}` | reject |
| MANAGER_FORCE_ACCEPT | Исполнено **или Возвращена** → Принято | role manager | `{reason?}` | reject |
| CANCEL | любой нетерминальный (вкл. Возвращена) → Отменена | manager; applicant-owner только из `Новая` | `{reason}` | reject |

Примечания:
- `MANAGER_RECONFIRM` отдельным действием НЕ нужен: после `MANAGER_RETURN_TO_WORK` доработка идёт обычным циклом (`Выполнена →[MANAGER_CONFIRM]→ Исполнено`).
- «Возвращена» наружу проецируется как `Исполнено` до обновления потребителей (Р3, переходный период).
- Telegram-композит `Выполнена+confirmed` («не принятые» менеджера) ⇒ в каноне это просто `Исполнено`; список «не принятых» = `Исполнено` старше N дней.
- Edits вне workflow (urgency/notes/description) — НЕ actions; через `validate_edits` под тем же `FOR UPDATE` (terminal-guard: `Принято`/`Отменена` заморожены).

## 4. Backfill mapping-table (PR3; по текущим прод-данным — no-op)

| Сочетание (status, confirmed, returned) | Канон | Примечание |
|---|---|---|
| (Новая, f, f) | Новая | as-is |
| (В работе/Закуп/Уточнение, f, f) | as-is | |
| (В работе, \*, t) | В работе | пост-возврат; return_* остаются историей |
| (Выполнена, f, f) | Выполнена | ждёт менеджера |
| (Выполнена, t, f) | **Исполнено** | главное сворачиваемое сочетание |
| (Выполнена, t, t) | Выполнена | reconfirm-промежуток legacy-Telegram → **quarantine** (вручную; в проде нет) |
| (Исполнено, \*, f) | Исполнено | |
| (Исполнено, \*, t) | **Возвращена** (Р3) | возвращена заявителем, ждёт разбора менеджером; в проде нет |
| (Принято, \*, \*) | Принято | терминал |
| (Отменена, \*, \*) | Отменена | терминал |
| прочее | **quarantine/fail** | не молча |

Postflight-инвариант: `0 строк, где status='Выполнена' AND manager_confirmed=true` + quarantine пуст. Поля не очищаются (Р6) → downgrade тривиален.

## 5. Следующие шаги

1. ~~Подтвердить Р3~~ ✅ подтверждено: возврат через менеджера, статус «Возвращена».
2. PR1: `utils/request_workflow.py` — типы (Action/TransitionPatch/ActionCommand/PrincipalRef/ActorContext), `plan_transition`, action-table из §3, PAYLOAD_SCHEMAS, зелёный AST-inventory-тест. HF-0-guard'ы приёмки/возврата обновить под «Возвращена» при cutover (не раньше — в legacy-кодировке возврат остаётся `Исполнено+is_returned`).
3. Constraints-фаза: preflight дублей Rating/active-assignment → миграция 018.
4. PR2-pre: dual-read предикаты (база уже есть — `utils/workflow_predicates.py` из HF-0; «Возвращена» добавляется в канон-ветку) + read-инвентаризация-гейт.
5. Сообщить InfraSafe о будущем wire-статусе «Возвращена» (до contract наружу идёт проекция `Исполнено` — их ничего не ломает; контракт обновить к PR4).
