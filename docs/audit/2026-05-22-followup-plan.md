# План дальнейших доработок — 2026-05-22

**Базовый бэклог:** `docs/audit/2026-05-20-backlog.md`
**Точка отсчёта:** main `732e365` (ARCH-014 merged, PR #23).

## Контекст

После merge ARCH-014 состояние:
- **P0:** 1 open hard-blocker (FIX-007) + 2 prod user-action (FIX-002, FIX-004).
- **P1:** 30 open, **P2:** 48 open, **P3:** 36 open.
- **ARCH-014 follow-up gaps** (не блокеры, из code review + QA PR #23).
- **80 pre-existing test failures** в сьюте (`utils/`, `invite_service`) — не ARCH-014, но фон скрывает регрессии.

Принцип последовательности: сначала вернуть видимость регрессий (зелёный CI), затем закрыть release gate, затем P1 по группам.

---

## Фаза 0 — Стабилизация (1-2 дня) — немедленно

Цель: зелёный test suite + CI, чтобы дальнейшие фазы не вносили скрытых регрессий.

### 0.1 — ARCH-014 follow-up (из review/QA PR #23)
| Задача | Что | Est. |
|---|---|---|
| WS accept-before-close | `/ws/v2/buildings`, `/kanban`, `/shifts` вызывают `close()` без `accept()` на auth-reject — один PR на три endpoint'а | 1 h |
| `AddressValidationError` dead code | core никогда не raise'ит — либо задействовать в `create_apartment` валидации, либо удалить класс + 422-ветку | 30 min |
| Тесты yard/apartment `.updated` emit | в `test_address_events.py` нет покрытия emit для yard/apartment update | 1 h |
| WS `/ws/v2/buildings` e2e | доставка события до подписчика не тестируется (AC4 partial) | 2 h |

### 0.2 — Триаж 80 pre-existing test failures
| Сьют | Фейлов | Гипотеза | Действие |
|---|---:|---|---|
| `utils/test_structured_logger.py` | часть из 65 | ожидает `[REDACTED]`, получает raw — **возможен реальный security-баг redaction** | диагностировать первым |
| `utils/test_redis_wrapper.py` | часть из 65 | API drift | диагностика → fix или retire |
| `utils/test_shift_scheduler.py` | часть из 65 | API drift | диагностика → fix или retire |
| `tests/services/test_invite_service.py` | 15 | `is_nonce_used` отсутствует на `InviteService` — тест рассинхрон; пересекается с SEC-020 (nonce TOCTOU) | сверить с актуальным API, переписать |

Итог фазы: `docker exec uk-management-bot pytest` — зелёный (или явный, документированный skip-list).

### 0.3 — CI enablers (промоут из P1)
- **OPS-109** — GitHub Actions pytest pipeline (2 h).
- **OPS-110** — `docker-compose.dev.yml` bind-mount source (30 min).

Поднять раньше остального P1: без CI «0 регрессий» в следующих фазах недоказуемо.

---

## Фаза 1 — Закрытие P0 release gate (2-3 дня)

После фазы проект становится releasable.

| ID | Задача | Est. | Примечание |
|---|---|---|---|
| **FIX-007** | Inbound webhook router + HMAC SHA-256 verification, nonce replay-protection, rate-limit | 4 h | Ungated после ARCH-014, единственный open P0 |
| **FIX-002 prod** | Ротация 7 секретов на production `.env` (runbook готов) | 30 min | Координированный INFRASAFE dual-secret flip с operator |
| **FIX-004 prod** | `ALTER ROLE uk_bot NOSUPERUSER` на production | 45 min | Runbook `docs/audit/runbooks/FIX-004.md` |
| **DB-111** | Переписать FIX-003 migration на `NOT VALID + VALIDATE` (prod-safe locking) | 1 h | Блокирует prod-deploy FIX-003 |
| **OPS-112** | Прогнать 8 verification-чеков webhook-hardening на проде | 1 h | PR-A/B/C/D в main (`a20686f`), но прод-инцидент 2026-05-19 не подтверждён закрытым |

---

## Фаза 2 — P1 безопасность + быстрые победы (3-4 дня)

Сгруппировано по риску. Быстрые (<30 min) делать первыми пачкой.

**Быстрые победы:**
- SEC-019 — rate-limit на `set-password` (10 min)
- SEC-018 — auth-store не персистить в localStorage (30 min)
- REFACTOR-030/031 — `sys.path.append` + lazy logger imports (25 min)
- BUG-024 — `web/api/invite.py` использует deprecated `user.role` (15 min)

**Безопасность (фронт + API boundary):**
- SEC-017 — TWA refresh token из localStorage в memory (2 h)
- SEC-020 — invite nonce TOCTOU race + advisory-lock (1 h) — синхронизировать с фиксом `test_invite_service` из фазы 0.2
- SEC-021 — валидация `request_number`/`category` в `media/upload` (30 min)
- SEC-022 — fail-fast при `DEBUG=False` + `ALLOWED_ORIGINS=*` (30 min)
- SEC-023 — DDL f-string в `add_performance_indices.py` (30 min)
- SEC-109 — Pydantic Field validation на `RegistrationData.full_name` (1 h)

---

## Фаза 3 — P1 архитектура и рефакторинг (1-2 недели)

ARCH-014 закрыл address-домен. Остаток P1-архитектуры:

- **ARCH-009** — два FastAPI app с расходящимися конфигами (включает ARCH-101, NICE-080)
- **ARCH-010** — детерминированный `event_id` в outbox (1 h) — всё ещё `uuid.uuid4()` в `build_building_payload`
- ~~ARCH-011~~ — ✅ resolved by `a20686f`, downgraded P1→P3 (косметика сортировки)
- **ARCH-012** — `api/main.py` смешивает 3 слоя (3 h)
- **ARCH-013** — `next(get_db())` без lifecycle в bot handlers (2 h)
- **ARCH-015** — `pair_with_next` плоская модель → rows (1 d)
- **ARCH-106** — миграция секретов в secret-manager (1-2 d) — закрывает корень FIX-002
- **REFACTOR-025/026/027** — дедуп `queue_webhook`, разбиение `address_service.py` / `addresses/router.py` (post-ARCH-014 файлы уже меньше — пере-оценить объём)
- **REFACTOR-032 / BUG-028** — f-string logging + PII, `except Exception` ×24
- **BUG-BOT-036** — `notify_user` asyncio.run в running loop

**FIX-008** (de-async 12 read-методов + 37 handler await-sites) — выполнять здесь как plain refactor.

---

## Фаза 4 — P2/P3 плановое (по остаточному принципу)

48 P2 + 36 P3: L10N quick fixes, frontend UX (FE-033..047), bundle splitting (FE-042), DB tech-debt (DB-103/104), data cleanup (BUG-BOT-017). Брать пачками по теме между крупными фазами.

---

## Оценка и порядок

| Фаза | Объём | Выход |
|---|---|---|
| 0 — Стабилизация | 1-2 дня | Зелёный CI, нет слепых зон |
| 1 — P0 gate | 2-3 дня | Проект releasable |
| 2 — P1 security | 3-4 дня | Закрыта поверхность атаки фронт/API |
| 3 — P1 архитектура | 1-2 недели | Снят основной arch-долг |
| 4 — P2/P3 | ~3-4 недели | Полировка |

**Критический путь до релиза:** Фаза 0 → Фаза 1. ~4-5 рабочих дней.

## Решения, требующие подтверждения

- Фаза 0.2: фиксить или retire'ить старые `utils/`-тесты — зависит от того, реальный ли баг redaction в `structured_logger`.
- ARCH-106: выбор платформы secret-manager (Doppler / 1Password / AWS-SM).
- FIX-002/FIX-004 prod — требуют доступа к production, выполняются пользователем.
