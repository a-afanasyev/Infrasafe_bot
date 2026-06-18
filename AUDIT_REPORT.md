# Аудит проекта UK Management — 2026-06-15

Полный read-only аудит монорепо (aiogram 3 бот + FastAPI API + React-дашборд + media_service, PostgreSQL/Alembic, Redis, Docker). Все находки подтверждены чтением кода; ссылки в формате `файл:строка`. Анализ распараллелен по фазам 1–5 через субагентов, результаты агрегированы; ключевые P1 перепроверены вручную.

> Это аудит #3. Предыдущий (#2, 2026-06-12, рев. `7ace460`) сохранён в истории git. Часть его P0 (outbox-сериализация доставки, frontend rules-of-hooks, мёртвые сервисы) с тех пор закрыта волнами closure-plan — этот аудит отражает текущее состояние `main` (`a6e52ff`).
> Метод: фазы 2–5 — параллельные субагенты; headline-находки (`user.role` в shift-сервисах, coverage-omit, set-password) перепроверены автором по исходникам.

---

## 1. Executive summary

Кодовая база зрелая и, для своего размера (~94k строк прод-кода), на удивление чистая и хорошо защищённая. Безопасность — выше среднего: ни одной P0-уязвимости, секреты не захардкожены и fail-fast в проде, JWT/IDOR/CORS/HMAC/rate-limit реализованы корректно с явными SEC-комментариями. Переусложнения нет: ни одной «абстракции на будущее», зависимости чистые, мёртвого кода почти нет.

Главный реальный риск — **корректность, а не безопасность**: автоназначение и планирование смен фильтруют исполнителей по устаревшему скалярному полю `user.role`, которое CLAUDE.md прямо запрещает (канон — JSON-массив `user.roles`). Исполнитель, у которого роль только в `roles`, невидим для автоназначения — пайплайн может молча находить ноль/не тех исполнителей. Независимо обнаружено двумя субагентами и подтверждено вручную (`shift_assignment_service.py:741,769,904`; `shift_planning_service.py:423`).

Архитектурный долг сконцентрирован в god-файлах хендлеров (shift_management.py 3966, requests.py 2869, admin.py 2855 строк) с прямым ORM в презентационном слое (252 вызова `db.query` в handlers/) и широкими `except Exception` (784 шт.). Инженерные пробелы — процессные: в CI нет сканеров безопасности (bandit/pip-audit/npm audit), mypy только в pre-commit (не в CI), покрытие измеряется, но не гейтится, а весь слой хендлеров исключён из покрытия; ruff проверяет только изменённые строки, оставляя ~670 нарушений в легаси. P0 нет; список действий управляем точечными PR.

---

## 2. Scorecard

| Фаза | Оценка | Обоснование |
|---|---|---|
| Архитектура | **6/10** | Сильный фундамент (outbox/webhook-resilience, разделение секретов, валидация outbound-URL), но god-файлы, ORM в хендлерах и легаси `user.role`. |
| Код | **6/10** | Хорошая транзакционная дисциплина в `request_service`, но P1-баг `user.role`, naive/aware datetime, пути без rollback, дублирование проверок ролей. |
| Простота | **8/10** | Нет dead-абстракций, фабрик, single-impl интерфейсов; зависимости чистые; только мелкий on-disk мусор. |
| Безопасность | **8/10** | Нет P0; корректные JWT/IDOR/CORS/HMAC/секреты/rate-limit; только P2/P3 hardening и транзитивные CVE. |
| Практики | **6/10** | Линейные миграции, блокирующие тесты, hash-pinned deps, pre-commit — но нет CI-security-scan, mypy вне CI, покрытие не гейтится (+ handlers исключены), нет README. |

---

## 3. Находки

Severity: **P0** критично · **P1** высокая · **P2** средняя · **P3** низкая. Effort: S/M/L.

| ID | Sev | Категория | Файл:строка | Описание | Рекомендация | Effort |
|---|---|---|---|---|---|---|
| F-01 | **P1** | Корректность / doc-vs-reality | `services/shift_assignment_service.py:741,769,904`; `services/shift_planning_service.py:423`; `handlers/shift_management.py:2998` | Автоназначение/планирование фильтруют исполнителей по **deprecated** `user.role` без fallback на `roles`-массив; CLAUDE.md запрещает `user.role` (дефолт `applicant`). Пайплайн может молча находить 0/не тех исполнителей. | Заменить на `User.roles.contains('executor')` / `auth_helpers.has_executor_access` (паттерн уже в `user_management_service.py:227`). | M |
| F-02 | **P1** | Практики / безопасность | `.github/workflows/ci.yml` | В CI нет никакого сканирования безопасности (bandit/pip-audit/npm audit/CodeQL/Trivy). | Добавить job `pip-audit` + `npm audit --audit-level=high`; опц. bandit/CodeQL. | M |
| F-03 | **P1** | Практики / типы | `.github/workflows/ci.yml`; `.pre-commit-config.yaml:26` | mypy есть только в pre-commit, в CI отсутствует → регрессии типов проходят, если контрибьютор пропустил pre-commit. | Добавить mypy-шаг в CI (scoped, non-blocking→ratchet). | M |
| F-04 | **P1** | Покрытие | `pyproject.toml:18-24` | Покрытие **не гейтится** (нет `--cov-fail-under`) и `omit` исключает весь `uk_management_bot/handlers/*` — слой хендлеров невидим для coverage. Правила требуют 80%. | Убрать `handlers/*` из omit (или мерить отдельно); добавить `--cov-fail-under=N` ratchet. | M |
| F-05 | **P2** | Конкурентность | `services/notification_service.py:498` | `notify_user` (sync) делает `loop.create_task(send_to_user(...))` без удержания ссылки — задача может быть GC'нута, ошибки доставки теряются. Критичный путь уже на `notify_user_async` (эта волна). | Хранить ref в set с done-callback или мигрировать оставшихся sync-вызывающих на `notify_user_async`. | M |
| F-06 | **P2** | Связность | `handlers/shift_management.py` 3966; `requests.py` 2869; `admin.py` 2855; `user_management.py` 2427 | God-файлы: несвязанные под-домены в одном (шаблоны+автоплан+планирование; review+invites+панели+закуп). Цель из правил — <800 строк. | Разбить по под-доменам. | L |
| F-07 | **P2** | Утечка слоёв | `handlers/admin.py` 52× `db.query`, `shift_management.py` 39×, `user_management.py` 16× — 252 в handlers/ | Прямой ORM + бизнес-логика в презентационном слое (`admin.py:109 auto_assign_request_by_category`). Нетестируемо без Telegram-объектов. | Вынести в `services/*`; хендлер → сервис → ответ. | L |
| F-08 | **P2** | Ресилентность | `services/redis_pubsub.py:22,39,61` | `aioredis.from_url(...)` без `socket_timeout`/`socket_connect_timeout` — зависший Redis блокирует publish/SSE бессрочно. | Добавить `socket_timeout`, `socket_connect_timeout`, `health_check_interval`. | S |
| F-09 | **P2** | Ресилентность | `services/notification_service.py:101,111,266,295,324,356` | `bot.send_message(...)` без per-call timeout; медленный Telegram стопорит broadcast-циклы. | Default request timeout на сессии бота / per-call `request_timeout`. | S |
| F-10 | **P2** | Обработка ошибок | handlers/ 784× `except Exception`, 13× `except: pass` (`shift_management.py` 79, `user_management.py` 51) | Широкий catch-and-continue прячет корневую причину за generic-сообщениями; 13 мест глушат полностью. | Сузить типы; гарантировать `exc_info=True`; убрать `pass`. | M |
| F-11 | **P2** | Корректность (tz) | `services/shift_assignment_service.py:992`; `services/shift_planning_service.py:452` | naive `datetime.now()` сравнивается с tz-aware `timestamptz` (пишется UTC) → смещение на UTC-offset сервера. | Везде `datetime.now(timezone.utc)`. | S |
| F-12 | **P2** | Корректность | `services/shift_assignment_service.py:1046` | `reassign_on_absence` в `except` возвращает ошибку **без** `self.db.rollback()` после мутаций — грязная сессия. | Добавить `rollback()` (паттерн из `request_service.py`). | S |
| F-13 | **P2** | Корректность | `services/shift_assignment_service.py:182` | Кандидаты сортируются по score, но оценивается только `[0]`; при конфликте у топа — провал без перебора. Ранжирование бесполезно. | Перебирать отсортированных до прохождения conflict-check. | M |
| F-14 | **P2** | Дублирование | `handlers/requests.py:1150,1304,1383,1488,1587,1900…` (10+ инлайн `active_role == "executor"`) | `auth_helpers` импортирован ~9 хендлерами; остальные дублируют сравнения строк ролей — дрейф, теряется multi-role кейс. | Все проверки ролей через `auth_helpers`. | M |
| F-15 | **P2** | Хрупкость | ~22 хендлера, `request_assignment.py:41` `callback.data.split("_")[-1]` | Парсинг callback-data строковым split без единого кодека; `_` в payload тихо ломает разбор. | aiogram `CallbackData`-фабрики / общий парсер. | M |
| F-16 | **P2** | Auth (A07) | `api/auth/router.py:343-360` + `auth/schemas.py:50` | `/auth/set-password` гейтится только `get_current_user`, нет `current_password` — валидный access-token молча перезаписывает пароль (фронт — «смена пароля»). | Требовать+проверять `current_password`, если `password_hash` уже задан. | S |
| F-17 | **P2** | Зависимости (A06) | `requirements.txt` (aiohttp 3.13.5) | 2 CVE в `aiohttp` (RCE `CookieJar.load`, cookie-leak). **Не эксплуатируется** (приложение на `httpx`, aiohttp транзитивный, `CookieJar.load` не вызывается). | Поднять aiohttp ≥3.14.0 при refresh deps. | S |
| F-18 | **P2** | Зависимости (A06) | `frontend/package-lock` (form-data 4.0.x) | High: CRLF-инъекция в транзитивном `form-data`; низкая эксплуатируемость (имена полей под контролем). | `npm audit fix` → ≥4.0.6. | S |
| F-19 | **P2** | Линтинг (scope) | `ci/ruff_changed_lines.py`; `pyproject.toml:33` | Ruff только по изменённым строкам → ~670 нарушений в легаси не чинятся; `media_service/scripts/docs` ещё `extend-exclude`. | Закрыть follow-up чистки → full-repo `ruff check` блокирующим. | L |
| F-20 | **P2** | Линтинг FE | `frontend/eslint.config.js`; `ci.yml:180` | ESLint не блокирующий (`continue-on-error`, ~59 ошибок) и не type-aware. `tsc -b` частично компенсирует. | Сжечь ошибки → убрать `continue-on-error`; typed-конфиг. | M |
| F-21 | **P2** | Документация | корень репо | Нет root `README.md` — онбординг на CLAUDE.md + `make help`. | Добавить README (стек, quickstart, тесты, env). | S |
| F-22 | **P2** | Мёртвый код | `handlers/requests.py:53-54` | Дублирующий + неиспользуемый импорт (`REQUEST_CATEGORIES`/`REQUEST_URGENCIES`; модуль читает `settings.REQUEST_CATEGORIES`). | Удалить обе строки. | S |
| F-23 | **P3** | Корректность | `services/shift_assignment_service.py:1214` | Тавтологичная ветка `elif any(spec in ... for spec in [request.specialization])` идентична предыдущему `if` → `+0.2` недостижим. | Удалить или реализовать fuzzy-match. | S |
| F-24 | **P3** | Качество тестов | `services/test_notification_service.py:134` | `assert "1" in msg` — подстрока матчит почти любой текст, длительность не проверяется. | Ассертить полную локализованную строку. | S |
| F-25 | **P3** | Качество тестов | `tests/test_shift_assignment_service.py:217+` | Скоринговые тесты мокают всю `db.query().filter().count()` — арифметика проверена, SQL-фильтры нет. | ≥1 sqlite-интеграционный тест на реальный запрос. | M |
| F-26 | **P3** | Качество тестов | `tests/test_request_workflow.py:50`, `test_handler_shifts.py:70`, `test_api_executor_shifts.py:373` | Хардкод дат; часть «active shift»-ассертов поплывёт с реальным временем. | freezegun / `utcnow`-фикстура. | M |
| F-27 | **P3** | Обработка ошибок | `services/shift_assignment_service.py:439,487` | Broad-except возвращает «безопасный дефолт» (0.5 / busy=True / None), маскируя DB-ошибки. | Сузить типы; давать ошибкам всплывать. | M |
| F-28 | **P3** | YAGNI | `config/settings.py:174` + `handlers/health.py:218` | Флаг `ENABLE_NOTIFICATIONS` ничего не гейтит кроме поля в health-JSON. | Подключить к notification-пути или удалить. | S |
| F-29 | **P3** | Мёртвый код | `utils/constants.py:115-135` | Блок `REQUEST_CATEGORIES` помечен `DEPRECATED`, держится из-за мёртвого импорта F-22. | После F-22 — удалить (~20 строк). | S |
| F-30 | **P3** | Чистота репо | `mappings/handlers_mapping.json` | Трекается в git, 0 ссылок в коде. | Подтвердить отсутствие внешнего потребителя → `git rm`. | S |
| F-31 | **P3** | Чистота репо | корень: `*.png` (~30, ~4–6 МБ), `ruvector.db`, `uk_management.db`, `.coverage`, `__pycache__/` | On-disk мусор в корне (gitignored, но захламляет дерево/IDE). | Удалить с диска / в `docs/`; gitignore `*.db`/`.coverage`. | S |
| F-32 | **P3** | Misconfig (A05) | `api/main.py:371-391` | `/api/v2/announcements` без auth (сейчас статичный плейсхолдер, утечки нет; риск при DB-backed). | `Depends(get_current_user)` при переводе на динамику. | S |
| F-33 | **P3** | Insecure Design (A04) | `api/rate_limit.py:32-40` | Rate-limiter **fail-open**: при падении Redis → per-worker in-memory счётчики (ослабляет brute-force login/registration). Митигировано SEC-062 алертом. | Пилот — accepted-risk; рассмотреть fail-closed на auth-роутах. | M |
| F-34 | **P3** | Logging (A09) | `api/main.py:514,618`; `integrations/media_client.py:118` | Логируется `resp.text[:200]` downstream media-сервиса — низкий риск, но захват неожиданных тел. | Логировать статус + статическое сообщение. | S |
| F-35 | **P3** | Misconfig (A05) — требует подтверждения | `api/rate_limit_keys.py:50-62` | Доверие `X-Real-IP` безопасно только при инварианте «api не торчит наружу, только nginx». При прямом экспозе — подделка обходит per-IP лимит. | Задать `RATE_LIMIT_TRUSTED_PROXIES` = peer-IP nginx в проде. | S |
| F-36 | **P3** | Конфиг | `config/settings.py` (`ADMIN_PASSWORD` dev-fallback; `INFRASAFE_SYSTEM_USER_TELEGRAM_ID=0`; прод-хосты в дефолте `CORS_ORIGINS`) | Безопасно в проде (raise при `not DEBUG`), но: молчаливый dev-пароль при случайном `DEBUG=true`; sentinel id `0` без валидации; прод-origin'ы захардкожены. | WARNING при dev-fallback; валидация id≠0; убрать прод-хосты из дефолта. | S |
| F-37 | **P3** | Конкурентность | `database/session.py:9,25,47,98` | Сосуществуют sync `SessionLocal` и async `AsyncSessionLocal`; sync-SQLAlchemy в aiogram-loop блокирует event loop под нагрузкой; `session_scope()` есть, но 0 потребителей. | Async для горячих путей / threadpool; миграция на `session_scope()`. | L |
| F-38 | **P3** | Релизы | репо-wide | Нет git-тегов/CHANGELOG; деплой — ручной `docker compose`; `images-build` без push; версия API захардкожена `2.0.0`. | Version-теги + CHANGELOG или явный release-runbook. | M |

### Чисто (без действий)
- **Зависимости Python/JS** — все используются; `requirements.txt` — корректный `uv pip compile --generate-hashes`; depcheck-флаг `tailwindcss` — false-positive (Tailwind v4 через vite-плагин).
- **Переусложнение** — нет ABC/Protocol/Factory/Strategy/single-impl интерфейсов в прод-коде.
- **Инъекции** — нет raw-SQL с интерполяцией (все `text()` статичны), нет `os.system/subprocess/eval`, LIKE-поиск экранирует `%_\`, SSRF нет (outbound-URL фиксирован env).
- **Утечки ресурсов** — все `next(get_db())` (169) спарены с `finally: close()`; aiohttp-сессий не текут; фоновые задачи API корректно `cancel()`+`await` на shutdown.
- **Миграции** — линейная история (один head `020`), без множественных голов.
- **Безопасность (сделано хорошо):** секреты fail-fast в проде + запрет `JWT_SECRET==INVITE_SECRET`; HS256 с выделенным секретом, MFA `iss/purpose`, OTP `SystemRandom`+`hmac.compare_digest`, токены `secrets.token_*`, bcrypt; IDOR-контроль через `check_request_access`/`dependencies_access`; CORS без wildcard, security-headers, httponly+secure+samesite cookies, `/docs` off в проде; Telegram initData HMAC с свежим `auth_date`.

---

## 4. Top-10 quick wins (макс. эффект / мин. усилия)

1. **F-01** — `user.role` → `roles.contains('executor')` в shift-сервисах (M; чинит молчаливый прод-баг автоназначения). 
2. **F-02** — `pip-audit` + `npm audit` в CI (M). 
3. **F-04** — убрать `handlers/*` из coverage-omit + `--cov-fail-under` (M). 
4. **F-22** — удалить дублирующий импорт `requests.py:53-54` (S). 
5. **F-16** — `current_password` в `/auth/set-password` (S). 
6. **F-17/F-18** — aiohttp ≥3.14, `npm audit fix` form-data (S). 
7. **F-08/F-09** — таймауты на Redis и `bot.send_message` (S). 
8. **F-11** — `datetime.now(timezone.utc)` в shift-запросах (S). 
9. **F-21** — root `README.md` (S). 
10. **F-03** — mypy в CI (non-blocking ratchet) (S добавить). 

---

## 5. Roadmap рефакторинга (P0→P2 с учётом зависимостей)

**P0:** нет.

**Волна 1 — Корректность + защита от регрессий (сначала, дёшево):**
1. F-01 (`user.role` в shift-сервисах) — прод-критичный баг автоназначения; одновременно F-25 (sqlite-тест на реальный SQL-фильтр) фиксирует поведение.
2. F-11, F-12, F-13 — корректность shift-сервисов (тот же модуль, вместе с F-01).
3. CI-гейты, чтобы долг не рос: F-02 (security-scan), F-03 (mypy), F-04 (coverage). Их — раньше крупного рефакторинга.

**Волна 2 — Точечные P2 (S/M, независимы):**
4. F-16 (set-password), F-17/F-18 (deps), F-08/F-09 (timeouts), F-22 (dead import), F-21 (README), F-05 (notify task-tracking).

**Волна 3 — Структурный долг (L, после гейтов и тестов):**
5. F-14 (роли через `auth_helpers`) + F-15 (кодек callback-data) — снижают дублирование, готовят к декомпозиции.
6. F-07 (вынести ORM/логику в сервисы) → затем F-06 (разбить god-файлы). Порядок: сначала логику в сервисы (тестируемо), потом дробить тонкие хендлеры. Требует F-04 (coverage на handlers) как страховку.
7. F-37 (async-DB / `session_scope()`) — самый дорогой, последним, инкрементально по горячим путям.

**Параллельно/фоном:** F-10 (сужение except), F-19/F-20 (линтинг), уборка P3 (F-23…F-38) по мере касания файлов.
