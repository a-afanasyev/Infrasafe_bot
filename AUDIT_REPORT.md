# Аудит проекта UK Management — 2026-07-11 (аудит #5)

Полный read-only аудит монорепо: aiogram 3 бот + FastAPI API + React-дашборд + `media_service` + `access_control`, PostgreSQL/Alembic (baseline 001+002), Redis, Docker. Все находки подтверждены чтением кода, ссылки `файл:строка`. Фазы 1–5 распараллелены по 6 субагентам (Arch / Code-bot / Code-API+FE / Dead-code / Security / Practices), агрегированы автором.

> Это аудит #5. Предыдущий (#4, 2026-07-02) — в истории git этого файла. С тех пор закрыты: SEC-01…06, COD-01…03, DED-01…03, ARC-03/04/05/06 (частично), PRC-01…05 (squash-baseline + B0-гейт), PRAC-01 ruff 663→0. Известные закрытые темы здесь не повторяются; известные осознанные остатки помечены.
> Метрики: ~169k строк Python (733 файла), ~37k строк TS/TSX (301 файл), 158+78+50 python-тест-файлов + 64 фронтовых.

---

## 1. Executive summary

Проект после четырёх волн аудитов — в заметно лучшей форме, чем годом раньше: **P0 не найдено, безопасность — сильнейшая фаза (8.5/10)** — секреты, инъекции, IDOR, JWT, Telegram-подписи, CORS/CSRF и логи чисты; pip-audit нашёл только транзитивные CVE вне пути эксплуатации, npm audit — 0. CI образцовый: все заявленные гейты (ruff, coverage 65%, pip-audit, B0 least-privilege, alembic-drift, guard:brand, двойная бренд-сборка) подтверждены реально существующими и blocking.

Найдено **два P1 — оба живые функциональные баги**, не уязвимости: (1) в боте approve/reject/delete сотрудника роняет перерисовку списка на парсинге `callback.data` — тот же баг, что уже чинился для block/unblock, остался в 3 местах; (2) исполнитель может создать несколько параллельных active-смен через `POST /executor/shifts/start`, после чего три эндпоинта (карточка сотрудника, TWA «текущая смена», overlap-проверки) падают 500 на `scalar_one_or_none()`.

Системный долг сконцентрирован в трёх местах: **shift-домен** — кластер несогласованностей (tz-naive/aware хаос в 5+ файлах бота, naive datetime в POST но не PATCH, from-template без overlap-проверки, TOCTOU в PATCH); **realtime-контур дашборда** — WS умирает навсегда без reconnect, optimistic-update канбана без серверной реконсиляции, мёртвые WS-соединения копят Redis-подписки; **`media_service` — сервис-сирота** вне всех CI-гейтов (тесты не гоняются, ruff исключён, образ не собирается). Плюс ~700 строк подтверждённого мёртвого кода в «аналитическом» кластере смен и fresh-install, невозможный по README (двойники env-примеров с несуществующими ключами).

Архитектурно опасного не осталось — долг сместился из «риск инцидента» в «трение при изменениях»: SQL в хендлерах шире, чем фиксировалось, 8 файлов >800 строк, 969 `except Exception` с log-and-swallow, двусторонняя связь ядра с access_control.

**Дополнение: внешний пентест profk.uz (codex_audit.md, 2026-07-11).** Отдельный black-box + статический аудит подтвердил отсутствие критических неаутентифицированных уязвимостей и добавил находки на стыке кода и **инфраструктуры/деплоя**, которые не видны из репозитория и потому отсутствовали в фазах 1–5: два High — runtime-контейнеры ходят в PostgreSQL под ролью-владельцем (она же миграционная), и auth-роутеры отдают `307`-редирект на `http://` без префикса `/uk` при trailing-slash (потеря HTTPS и маршрутизация POST-тела в чужой сервис); плюс refresh-token без атомарной ротации (гонка double-issue), WebSocket без live-ревалидации ролей и без timeout на неаутентифицированный handshake, отсутствие security-заголовков на `/uk/` HTML/JS (per-location `add_header` в nginx отменяет унаследованные), и набор DNS/TLS/hardening-замечаний. Уникальные пункты сведены в **Приложение П** ниже. Пересечения с фазами 1–5 (aiohttp→SEC-NEW-1, CSV-injection→APIFE-12, refresh-replay→APIFE-14, ecdsa→SEC-NEW-1) не дублируются.

---

## 2. Scorecard (1–10)

| Фаза | Оценка | Обоснование |
|------|:---:|------|
| **Архитектура** | **7** | Outbox с lease/CAS, advisory-lock реконсиляция, идемпотентный inbox и fail-fast конфиг — выше среднего продакшена; тянут вниз размытая граница handler/router↔сервис, 8 god-файлов и тотальный `except Exception`. |
| **Код** | **7** | Бот 6.5 (P1-баг, tz-хаос, копипаста карточек/парсеров), API 7.5 (последовательный IDOR-гейтинг, но кластер дыр shift-домена), фронт 7 (дисциплина хорошая, realtime хрупкий). |
| **Простота** | **7** | Мёртвый код не размазан, а сконцентрирован в 2 кластерах (~700 строк + edge-заготовка ~1150 после решения владельца); архитектурных излишеств в живом коде почти нет. |
| **Безопасность** | **8.5** | Все категории OWASP чисты; только транзитивные CVE вне пути эксплуатации и мелкая крипто-гигиена (md5-идентификатор, нет floor длины JWT_SECRET). |
| **Практики** | **8** | CI и миграционная дисциплина (B0-гейт, ratchet-философия) — 9–10; снимают балл media_service вне гейтов, нерабочий fresh-install и отсутствие релизных тегов. |

---

## 3. Находки

**P0 — критично: нет.**

### P1 — высокая

| ID | Категория | Файл:строка | Описание | Рекомендация | Объём |
|----|-----------|-------------|----------|--------------|:---:|
| CODE-1 | Корректность (бот) | `uk_management_bot/handlers/employee_management.py:393,445,914` | После approve/reject/delete вызывается `show_employee_list`, но `callback.data`=`approve_employee_<id>` парсится как `employee_mgmt_list_<type>_<page>` → IndexError, список не рендерится, карточка stale (кнопка «Одобрить» видна после одобрения). Тот же баг чинился для block/unblock (MGR-05, коммент :555-558) — 3 сайта остались. | Заменить на `_return_to_employee_info(...)` как в block/unblock + регресс-тест. | S |
| APIFE-1 | Корректность (API) | `uk_management_bot/api/shifts/executor_router.py:133-150`; `api/shifts/service.py:314-317,679-695`; `executor_router.py:107-110` | `POST /executor/shifts/start` создаёт active-смену без guard'а уже активной (менеджерский POST проверяет — `shifts/router.py:779-787`). При >1 active три места падают `MultipleResultsFound`→500: карточка сотрудника, `GET /executor/shifts/current` (TWA), overlap-проверка create/patch/reassign. | Guard «одна active-смена на исполнителя» в `/start`; `scalar_one_or_none()`→`.first()` в трёх читателях. | M |

### P2 — средняя

| ID | Категория | Файл:строка | Описание | Рекомендация | Объём |
|----|-----------|-------------|----------|--------------|:---:|
| CODE-3 | Корректность (бот) | `handlers/my_shifts.py:470,523,531`; `handlers/shifts.py:151,210`; `utils/shift_scheduler.py:402` | Системный tz-naive/aware хаос в сменах: naive-local `datetime.now()` пишется в timestamptz; длительность = naive-now − UTC-стрип → врёт на смещение TZ; соседний `_notify_upcoming_shifts:355` уже починен (QA-04), остальные — нет. | Единый хелпер `utc_now()`, сравнение только aware; пройти все 6 сайтов разом. | M |
| CODE-2 | Корректность (бот) | `services/shift_service.py:251-254` | `get_shift_stats`: naive `now` минус tz-aware `start_time` → TypeError, глотается `except` → нули. Сейчас latent (вызовы только из тестов), мина при подключении. | Часть волны CODE-3. | S |
| CODE-4 | Тесты | `uk_management_bot/test_auth_fixes.py` | Псевдо-тест в git, собирается pytest'ом (testpaths=`uk_management_bot`): ни одного assert (всегда зелёный), при этом `Base.metadata.create_all` против реального `DATABASE_URL` — side-effect в «тесте». | Удалить (или переписать на assert + sqlite-conftest). | S |
| CODE-5 | Конкурентность (бот) | `utils/shift_scheduler.py` (все job'ы) | Тяжёлые sync-SQLAlchemy батчи (rebalance, auto-assign, weekly planning) в async-job'ах на event loop бота → на время батча блокируются все хендлеры. Сессии закрываются корректно. | `asyncio.to_thread`/`run_in_executor` для тела job'а. | M |
| APIFE-2 | Ресурсы (API/WS) | `api/ws/router.py:110-194` | WS-хендлер после auth уходит в `pubsub.listen()`, `receive()` не вызывается → разрыв клиента замечается только при следующей публикации; на тихом канале закрытые вкладки копят Redis-подписки бессрочно. Тело хендлера скопировано 3× дословно. | Общий хелпер + задача-сторож `websocket.receive()` (отмена listen при disconnect) или ping. | M |
| APIFE-3 | Корректность (API) | `api/requests/router.py:164-175` | Канбан: `limit(500)` по `created_at desc` без фильтра терминальных статусов — «Принято»/«Отменена» копятся, по достижении 500 старые активные карточки исчезают с доски, `count` врёт. | Исключить терминальные старше N дней из выборки. | S |
| APIFE-4 | Корректность (API) | `api/shifts/router.py:761-793` vs `:843-847`; `api/shifts/schemas.py:145-159` | PATCH нормализует naive datetime→UTC, POST (`create_shift` + `CreateShiftBody`) принимает naive как есть → смена может встать со сдвигом, overlap-сравнение несогласованно. | `field_validator` в схеме — одно место на оба пути. | S |
| APIFE-5 | Корректность (API) | `api/shifts/router.py:590-627`; `api/shifts/service.py:570-600` | `POST /shifts/from-template` не проверяет пересечения (прямое создание и reassign — проверяют) → массовый double-booking. | Прогнать `find_overlapping_shift_for_update` по каждому user_id до вставки. | S |
| APIFE-6 | Контракт (API) | `api/board_config/schemas.py:74-96`; `api/requests/schemas.py:150` | Известная грабля «pydantic молча выкидывает неизвестные поля» не закрыта конфигом: `BoardConfigData` — тело PUT, забытое в схеме поле снова молча потеряется (уже стреляло с `width`). | `model_config = ConfigDict(extra="forbid")` на PUT-схемы board_config (+ желательно `UpdateRequestBody`). | S |
| APIFE-7 | Корректность (FE) | `frontend/src/hooks/useWebSocket.ts:37-49` | Realtime умирает навсегда: код 1008 (протухший cookie на upgrade) → «don't retry»; иначе 5 попыток и стоп; `refreshSession()` не дёргается, после сна ноутбука реконнекта нет — деградация до поллинга-по-фокусу. | На 1008 — `refreshSession().then(connect)`; сброс попыток на `online`/`visibilitychange`. | M |
| APIFE-8 | Корректность (FE) | `frontend/src/components/kanban/KanbanBoard.tsx:111-147`; `hooks/useKanban.ts:34` | Optimistic-update пишет в захардкоженный ключ `['kanban', {}]` (совпадает с реальным только пока фильтров нет); при успехе PATCH ни invalidate, ни применения ответа — реконсиляция только через WS, который может быть мёртв (APIFE-7). | `invalidateQueries({queryKey:['kanban']})` в `finally` или `setQueryData` из ответа. | S |
| ARCH-1 | Слои | `handlers/my_shifts.py:104,118` + `shift_transfer.py` (14 сайтов), `request_acceptance.py` (12), `employee_management.py` (12) и далее | Известный остаток, масштаб больше фиксировавшегося: ORM-запросы практически во всех aiogram-хендлерах; граница «handler = только UI» не выдерживается. | Не big-bang: при каждом касании хендлера выносить запросы в сервис (образец `services/admin_handler_service.py`). | L |
| ARCH-2 | Слои | `api/requests/router.py:315-358,449,654,711` + callcenter/profile/materials/public/board_config | Толстых роутеров больше отложенного ARC-06-списка: прямые query+commit в 9 роутерах; самый горячий — requests (751 строка, `_persist_request` с ретраем коллизий). | Следующий кандидат — `api/requests/router.py` по образцу `api/shifts/service.py`. | M |
| ARCH-3 | Связанность | `handlers/employee_management.py` (1572), `services/shift_assignment_service.py` (1363, 5 классов в одном файле), `shift_planning_service.py` (1283), `handlers/address_apartments.py` (1222), `access_control/api/registry.py` (1157), `services/address_service.py` (1085), `api/shifts/service.py` (1018), `api/shifts/router.py` (959) | 8 файлов нарушают правило AUD3-06 «<800 строк»; ARC-03 сделал логическую декомпозицию shift_assignment, файловой нет. | Механика block-move отработана; приоритет — employee_management.py и разнос классов shift_assignment по модулям. | M |
| ARCH-4 | Границы | `access_control/api/registry.py:30-35`, `domain/territory.py:20`, `app/main.py:43` ↔ `handlers/access_control.py:27`, `services/access_notify_subscriber.py:36` | Двусторонняя связь ядра и access_control (~15+ модулей импортируют ядро, ядро импортирует обратно): граница деплойная, не кодовая; выделение сервиса невозможно. | Минимум: зафиксировать contract-слой и AST-гейт на импорты domain↔domain. | S(гейт)/L |
| ARCH-5 | Ошибки | `services/notification_service.py:31-46,113-115`; `main.py:299-327`; 969 сайтов вне тестов | Доминирует log-and-swallow `except Exception`; глобальный обработчик бота всегда `return True`; проглоченное не попадает в подключённый Sentry. Образец правильного — только addresses (`api/addresses/exception_handlers.py`). | Не переписывать массово; для money-path'ов (create/accept/assign) — узкие исключения + `logger.exception`. | L |
| SEC-NEW-1 | Зависимости | `requirements.txt` (aiohttp 3.13.5, ecdsa 0.19.2) | pip-audit: 11 CVE в aiohttp (транзитивно от aiogram, клиент к доверенному api.telegram.org; CVE в основном server-side) + PYSEC в ecdsa (тянется python-jose, но JWT=HS256, ES-путь не задействован). Эксплуатируемого пути нет, floor устарел. | Bump aiohttp→3.14.1, ecdsa→fix; или замена python-jose на PyJWT. npm audit: 0. | S |
| PRAC-1 | Onboarding | `env.example`, `.env.example`, `README.md:38` | Fresh-install по README невозможен: README указывает на `env.example` с несуществующими ключами `SECRET_KEY`/`JWT_SECRET_KEY` (код читает `JWT_SECRET` — `settings.py:110`) и без обязательных `JWT_SECRET`/`INVITE_SECRET`/`UK_WEBHOOK_SECRET`/`ADMIN_PASSWORD`; `.env.example` лучше, но тоже неполный. Плюс мусорные `env.copy*` в корне. | Один канонический `.env.example` со всеми обязательными переменными, удалить дубли, поправить README. | S |
| PRAC-2 | CI | `.github/workflows/ci.yml` (отсутствие джобы); `pyproject.toml:48` | `media_service/` — живой прод-сервис с 5 тест-файлами и своим pytest.ini, но: тесты не гоняются ни одной джобой, образ не собирается в images-build, каталог исключён из ruff. Полностью вне всех гейтов. | Джоба media-tests + сборка образа + вернуть в ruff-scope. | M |
| PRAC-3 | Версионирование | git tags (один: `phase2b-deployment`) | Релизов/тегов/CHANGELOG нет; деплой = `git pull` main → «прод-указатель дрейфует» (уже кусало). Conventional commits идеальны — материал для автогенерации есть. | Annotated-тег на каждый деплой (`profk-YYYY-MM-DD`). | S |
| DEAD-1 | Мёртвый код | `services/recommendation_engine.py:129-375,652-800` | 3 публичных метода без единого вызова + 8 эксклюзивных хелперов; живой путь только `generate_comprehensive_recommendations`. | Удалить методы (~400 строк), модуль оставить. | M |
| DEAD-2 | Мёртвый код | `services/metrics_manager.py:328-528,843-932` | Единственный внешний вызов — `calculate_period_metrics`; `calculate_all_metrics`/`get_metrics_dashboard`/`get_performance_trends` + хелперы мертвы, тестами не покрыты. | Удалить (~290 строк). | M |
| DEAD-3 | Мёртвый код (решение) | `access_control/edge/` (~645 строк), `access_control/integrations/relay.py` | `command_consumer`/`snapshot_verifier` импортируются только тестами; pull-модель отвергнута решением о топологии Б (2026-07-03), HTTPRelay — задокументированный «скелет под будущее». | После подтверждения владельца: удалить edge/ + relay + ~5 тест-файлов (~1150 строк); судьбу `anpr_simulator` уточнить (QA-стенд?). | L |

### P3 — низкая

| ID | Категория | Файл:строка | Описание | Рекомендация | Объём |
|----|-----------|-------------|----------|--------------|:---:|
| CODE-6 | Ресурсы (бот) | `main.py:245`; `handlers/requests/listing.py` (весь); `keyboards/base.py:32` (~30 колл-сайтов) | До 3 сессий БД на один update: middleware + `_db_scope(None)` в хендлере + своя сессия в `get_user_contextual_keyboard`; пул 10+10. | Прокидывать инъецированную `db`. | M |
| CODE-7 | Ошибки (бот) | `keyboards/base.py:54-55` | `except Exception: return get_main_keyboard()` — сбой БД молча даёт applicant-клавиатуру (маскировка инцидентов). | Логировать + пробрасывать. | S |
| CODE-8 | Дублирование (бот) | `employee_management.py:69-95≈300-341≈_return_to_employee_info`; парсинг специализаций 7 копий (`listing.py:240,407`; `employee_management.py:962,1487`; `shifts.py:157,216`; `specialization_service.py:278`) при живом каноне `utils/specializations.py:16`; `_format_*_name` 4 копии | Копии уже расходятся (fallback `getattr(employee,"role")` только в одной); блок «права+alert» повторён ~15×. | Свести к канон-хелперам, декоратор для прав. | M |
| CODE-9 | Дублирование (бот) | `handlers/requests/listing.py:417-419` vs `:302` | Две реализации предиката «на смене» в одном файле (naive `datetime.now()` vs канон `is_on_shift_now_sync`). | Оставить канон. | S |
| CODE-10 | Читаемость (бот) | 44 функции >100 строк: `listing.py:367` (179), `:188` (175), `shift_management/assignment_b.py:413` (158), `auth_service.py:616 delete_user` (137, каскад 11 шагов руками) | Гигантские функции; delete_user — кандидат на FK ondelete. | Инкрементально при касании. | L |
| CODE-11 | Производительность (бот) | `listing.py:92-106` | In-memory пагинация: грузятся ВСЕ заявки пользователя, срез в Python (соседний `:424` уже на БД-пагинации). | Перевести на БД-пагинацию. | S |
| CODE-12 | Локализация (бот) | `employee_management.py:158,393,445,914`; `user_apartment_selection.py:407,416` | Внутренние перевызовы без `language` → UZ-пользователь получает RU-экран; admin-уведомление хардкодит 'ru' и тихо теряется при `bot=None`. | Прокидывать language. | S |
| CODE-13 | Ошибки (бот) | 806 сайтов `except Exception` в зоне бота (13 с голым pass) | Всё превращается в «unknown_error»-alert без re-raise при уже логирующем middleware. | Точечно сузить в money-path'ах (входит в ARCH-5). | L |
| APIFE-9 | Корректность (API) | `api/requests/router.py:595-601` | Распаковка `row` без проверки None после workflow-перехода → при конкурентном удалении TypeError→500 вместо 404. | Проверка None. | S |
| APIFE-10 | Валидация (API) | `api/requests/router.py:186` | `offset: int = Query(0)` без `ge=0` → отрицательный offset → ошибка Postgres → 500 (в shifts/materials везде `ge=0`). | Добавить `ge=0`. | S |
| APIFE-11 | Конкурентность (API) | `api/shifts/router.py:857-868` | Overlap-check в PATCH с `lock=False` — TOCTOU-гонка double-booking (create-путь лочит). | `lock=True`. | S |
| APIFE-12 | Безопасность (API) | `api/materials/router.py:239-262,285-303` | CSV formula injection: `supplier`/`reason`/имя материала уходят в Excel-CSV сырыми (`=`/`+`/`-`/`@` исполнится как формула). | Префиксовать `'` опасные значения. | S |
| APIFE-13 | Дублирование (API) | `api/requests/router.py:66`, `api/shifts/router.py:70`, `executor_router.py:186`; `routes/media_proxy.py:60` + `feedback/router.py:52` | Форматирование имени исполнителя — 3 расходящиеся копии; magic-byte sniffing — 2 копии. | Общие хелперы. | S |
| APIFE-14 | Хардининг (API) | `api/auth/router.py:279-299` | Нет reuse-detection при ротации refresh-токена: реплей ревокнутого → просто 401, семейство не отзывается. | Отзывать семейство при реплее. | M |
| APIFE-15 | Ресурсы (API) | `api/routes/media_proxy.py:231-248` | Файл до 50 МБ буферизуется в память целиком (`resp.content`) вместо стриминга. | StreamingResponse. | S |
| APIFE-16 | Корректность (FE) | `RequestDetailModal.tsx:46-66`; `transitions.ts:5` | В картах STATUS/STATUS_DOT нет «Возвращена» (бейдж молча серый); коммент «Must mirror backend …» ссылается на удалённую матрицу — ложный ориентир. | Добавить статус, поправить коммент. | S |
| APIFE-17 | UX/i18n (FE) | `LoginPage.tsx:141,143,156-160` | OTP-путь логина теряет `?next=` deep-link (`navigate('/dashboard')`); 3 строки мимо i18n. | `navigate(next)` + ключи i18n. | S |
| APIFE-18 | Гейт (FE) | `frontend/scripts/check-brand-hardcodes.mjs:33-40` | guard:brand ловит только 4 hex + имена лого; не поймает `rgb()`, новый оттенок, hex в .css/inline-style. Статус-палитра канбана продублирована сырыми hex в 2 файлах (не бренд, но дрейф-риск). | Расширить паттерны; палитру статусов — в общий модуль. | S |
| APIFE-19 | Тесты | `tests/api/test_shift_schemas.py` (582) и `uk_management_bot/api/shifts/test_schemas.py` (562) | Два сьюта тестируют один `api/shifts/schemas.py` — двойная стоимость поддержки. Co-located тесты в `api/` — конвенция проекта (сами тесты качественные), но тестовый код едет в прод-образ. | Консолидировать в tests/api. | S |
| SEC-NEW-2 | Крипто-гигиена | `handlers/auth.py:163` | `hashlib.md5(token)[:16]` как UX-идентификатор инвайта в FSM (не auth-критично, верификация — HMAC в invite_service), но md5 всплывает в SAST. | `sha256(...)[:16]`. | S |
| SEC-NEW-3 | Конфиг | `config/settings.py:110-115` | Прод-валидация проверяет наличие `JWT_SECRET`, не длину: короткий секрет HS256 брутфорсится оффлайн. Смягчено ротацией сильными значениями. | Guard `len < 32 → raise` (по образцу ADMIN_PASSWORD :258). | S |
| SEC-NEW-4 | Конфиг (требует подтверждения) | `access_control/edge/anpr_simulator.py:48` | Дефолтный `api_key="pilot-test-device-key"` в тест-симуляторе; эксплуатируем только если симулятор в проде и ключ провижинен. Снимается вместе с DEAD-3. | Сделать аргумент обязательным (или удалить с edge/). | S |
| ARCH-6 | Конфиг | `config/settings.py:52-274`; `main.py:213`; `docker-compose.yml:152` | Plain-класс Settings: env на import, ValueError в class-body, рантайм-мутация `BOT_USERNAME`; дефолт `MEDIA_SERVICE_URL=localhost:8001` расходится с compose. Плюсы: fail-fast секреты. | pydantic-settings при удобном случае; не срочно. | M |
| ARCH-7 | Конкурентность (требует подтверждения) | `utils/shift_scheduler.py:453` | Гонка авто-назначения планировщика (процесс бота) против ручного назначения из дашборда (процесс API) — наличие row-lock/статус-guard не проверено. | Проверить и при необходимости добавить guard. | S |
| PRAC-4 | CI | `tests/e2e/` (Playwright, 3 спеки) | В репо, но не подключены ни к одной CI-джобе — тухнут молча. | Workflow на dispatch/nightly против stage или пометить как ручной инструмент. | M |
| PRAC-5 | Типизация | `ci.yml:60-62` | mypy advisory без ratchet: 3118 ошибок могут расти бесконечно незаметно. | Ratchet: fail при превышении baseline-числа. | S |
| PRAC-6 | Тесты (FE) | `frontend/vitest.config.ts:47-61` | Floor lines=26/functions=17; из знаменателя исключены `src/twa/**`, `pages/twa/**`, `ui/**`, App.tsx — TWA (прод-поверхность) с нулевым тест-гейтом. | Следующая фаза ratchet — снять исключение twa. | M |
| PRAC-7 | Документация | `docs/` (корень) | 🔴-файлы, которые сам индекс называет «вводят в заблуждение», лежат вперемешку с актуальными; дубль с опечаткой `РАЗДЕЛ_2_СИСТЕМА_ЗАЯВКОВ.md`/`ЗАЯВОК.md`. | Перенести ⚫/🔴 в docs/Archive/. | M |
| PRAC-8 | Документация | `api/main.py:57-61` | OpenAPI в prod выключен (осознанно), но обещанного снапшота openapi.json в репо нет. | CI-шаг: `app.openapi()` → файл в repo + diff-гейт. | S |
| PRAC-9 | Тулчейн | `requirements-dev.txt:6-7`, `.pre-commit-config.yaml` | flake8 остался при вытеснившем его ruff; black/isort можно свернуть в ruff format/I. | Выкинуть flake8; остальное по желанию. | S |
| PRAC-10 | Гигиена | корень репо | ~50 untracked PNG, `uk_management.db`, `ruvector.db`, `env.copy*` — риск случайного `git add -A` (прецедент был). | `/*.png`, `*.db` в .gitignore явно. | S |
| PRAC-11 | Известный хвост | `pyproject.toml:42-49` | PRAC-01-FU2 открыт: `media_service`, `scripts` вне ruff-scope (~169 E/F). Фиксация, чтобы не потерялся. | Закрыть вместе с PRAC-2. | M |
| DEAD-4 | Мёртвый код | `services/assignment_service.py:27-33,389-391` | try/except ImportError вокруг импорта собственного модуля → флаг всегда True, ветки недостижимы. | Обычный импорт (~10 строк). | S |
| DEAD-5 | Мёртвый код | `uk_management_bot/requirements.txt` (0 байт); `Dockerfile:29,49`; `Dockerfile.dev:20,27` | Пустой файл копируется и скармливается pip install в двух Dockerfile. | Удалить файл + 4 строки. | S |
| DEAD-6 | Мусор | `uk_management_bot/api/notifications/` | Пустой каталог (только `__pycache__`) — останки DEAD-08. | Локальная чистка. | S |
| DEP-1 | Зависимости | `requirements-dev.txt` | flake8 (см. PRAC-9); `pytest-html`, `pytest-xdist` не упоминаются в CI/Makefile (требует подтверждения — возможно, локальная привычка). | −3 dev-зависимости. | S |
| DEP-2 | Зависимости (FE) | `frontend/package.json` | Монолитный `radix-ui` используется одним файлом при параллельных scoped `@radix-ui/*`. `date-fns` — обязательный peer, оставить. | Свести к одному стилю, −1 зависимость. | S |
| YAGNI-1 | Конфиг | `config/settings.py` | 15 из 39 env-ручек нигде не переопределяются (тюнинг outbox и т.п.). `RECONCILE_REQUESTS_ENABLED` (default false) — если не включён на проде, reconcile-путь `api/lifecycle.py:48` мёртв в рантайме (требует подтверждения ssh). | Зафиксировать константами; проверить прод-env. | S-M |
| JUNK-1 | Мусор (tracked) | корень: `uz-board.yml`, `test-media-service.sh`, `UK-WEBHOOK-SENDER-SERVICE-TZ.md` | Дамп снапшота, старый смоук, ТЗ — не место в корне. | Удалить / в scripts/ / в docs/. | S |
| JUNK-2 | Мусор (tracked) | `media_service/frontend/`, `TEST_REPORT.md`, `test_frontend.py`, `channels.json` | Тестовый фронт не деплоится; `channels.json` рядом с example — проверить, не рабочий ли конфиг (тогда не место в git). | Удалить ~10 файлов; проверить channels.json. | S |
| JUNK-3 | Мусор (решение) | `Caddyfile` | Не референсится ни одним compose; прод за nginx/InfraSafe (известный orphan uk-caddy). | Удалить или задокументировать назначение. | S |
| JUNK-4 | Untracked (решение) | `ProFK/`, `.codex/`, `.agents/`, `AGENTS.md`, `docs/user-guide/02-resident.pdf` | ProFK — исходники бренда (рекомендация: закоммитить в `docs/brand/profk/`); `.codex`/`.agents` — в .gitignore; AGENTS.md — коммитить только если готовы синхронить с CLAUDE.md; PDF — не трекать. | Разобрать по списку. | S |
| JUNK-5 | Мусор (диск) | `uk_management_bot/venv/` (148 МБ, python3.13, следы asset-bot), `ruvector.db`, PNG в корне | Локальный мусор, в git не попадает. | Удалить локально. | S |

### Чистые категории (проверено, проблем нет)

- **Безопасность**: секреты (git + код + история — ротация 2026-05-30), SQL/command/path-инъекции, IDOR (`check_request_access` последовательно), JWT (HS256 фиксированный, purpose-гейт), Telegram initData/Widget (HMAC + anti-replay 300с), OTP (CSPRNG + compare_digest + rate-limit fail-closed), CORS/headers/CSRF (SameSite=strict), SSRF/open redirect, загрузка файлов (magic bytes + 50MB + IDOR-gate), логи без PII/токенов.
- **Конкурентность инфраструктуры**: outbox (claim/lease + `FOR UPDATE SKIP LOCKED` + CAS), реконсиляция (`pg_try_advisory_lock`), идемпотентный webhook-inbox, APScheduler `max_instances=1`.
- **`next(get_db())`** — 0 боевых остатков (ARC-05 фактически закрыт, лучше заявленного); `user.role` — боевых обращений нет; `asyncio.run` в loop — нет.
- **N+1 в API** — не найдено (везде batch-load); пагинация с `le=200` (кроме kanban-cap — APIFE-3); Zustand — один аккуратный store; бренд-токены в компонентах соблюдаются.
- **Документация ↔ код**: `docs/tech/ARCHITECTURE.md` (2026-07-06) сверен выборочно — совпадает; CLAUDE.md актуален.
- **Лучшее место кодовой базы**: `utils/request_workflow.py` — чистый SSOT-модуль без I/O с полной action-таблицей + 710-строчный тест.

---

## 3-П. Приложение — уникальные находки внешнего пентеста (codex_audit.md)

Источник: `codex_audit.md` (2026-07-11), неразрушающий black-box + статический аудит + dependency-audit против живого `profk.uz`. Ниже — только пункты, которых **нет** в фазах 1–5 (пересечения F-06/F-07/F-18 опущены как дубли SEC-NEW-1/APIFE-12). Классы риска смещены в сторону инфраструктуры и деплоя — это и есть ценность внешнего взгляда поверх статического аудита кода. Code-citable пункты (F-01/02/03/08/11/17) перепроверены мной по исходникам и помечены ✓; чисто инфраструктурные (DNS/TLS/nginx на edge) приняты по отчёту пентеста как «black-box».

### High

| ID | Категория | Файл:строка / поверхность | Описание | Рекомендация | Объём |
|----|-----------|---------------------------|----------|--------------|:---:|
| PENT-F01 ✓ | Least privilege (БД) | `docker-compose.profk.yml:32,62,99,127-130`; `scripts/init_postgres.sql:2-10`; `scripts/entrypoint-api.sh:3-5` | Бот, API и Access API ходят в PostgreSQL под одной ролью `${POSTGRES_USER}` (комментарий compose:14 называет `profk_bot` суперюзером-владельцем), и та же роль запускает Alembic на старте API → runtime-роль = миграционная = владелец. Компрометация любого сервиса даёт DDL, правку аудита, создание ролей. **Расхождение с внутренней памятью «least-privilege внедрён»**: B0-CI-гейт доказывает лишь, что миграции *способны* идти под ограниченной ролью; фактический прод-compose всё ещё использует роль-владельца для runtime. **Требует подтверждения текущего состояния роли на проде по ssh** (демоут superuser мог быть сделан вручную, но единственность роли runtime≡migration — факт по compose). | Отдельная `uk_migration_owner` для Alembic (deploy-задача) + непривилегированные runtime-роли bot/API/access с только DML/sequence-грантами; не отдавать migration-credential в runtime-контейнеры. | L |
| PENT-F03 ✓ | Reverse-proxy / routing | `Dockerfile.api:84` (uvicorn без `--root-path`/`--proxy-headers`/`--forwarded-allow-ips`); `uk_management_bot/api/main.py:64` (`FastAPI()` без `root_path`, дефолтный `redirect_slashes=True`) | Trailing-slash на auth-маршруте даёт `307 Location: http://profk.uz/api/v2/auth/login` — теряется схема HTTPS и внешний префикс `/uk`, POST-тело (пароль/refresh) уходит в корневой InfraSafe-API (в пробе вернул «Access token is missing»); клиент без HSTS может повторить тело по plaintext HTTP. | nginx `X-Forwarded-Proto $scheme`; uvicorn `--proxy-headers --forwarded-allow-ips <nginx CIDR>` + ASGI `root_path=/uk`; для auth API отключить авторедирект слэша или объявить точные маршруты; регресс-тест: trailing-slash → 404 либо HTTPS-Location с `/uk`. | M |

### Medium

| ID | Категория | Файл:строка / поверхность | Описание | Рекомендация | Объём |
|----|-----------|---------------------------|----------|--------------|:---:|
| PENT-F02 ✓ | Session (гонка) | `uk_management_bot/api/auth/router.py:279-300` | Дополняет APIFE-14 стороной конкурентности: refresh читает токен обычным `SELECT`, затем меняет `revoked_at` и создаёт новый — без row-lock и без атомарного conditional-update. Два параллельных запроса видят токен валидным и выпускают две независимые сессии. | `UPDATE … WHERE revoked_at IS NULL … RETURNING` или `SELECT … FOR UPDATE`; хранить token-family, при повторе ротированного отзывать всю family; конкурентный PG-regression-тест. | M |
| PENT-F04 | Broken access control (WS) | `uk_management_bot/api/ws/router.py:71-107`; `access_control/api/ws_security.py:19-21,96-118` | WS проверяет роли только из JWT при handshake, БД-статус/актуальные роли не читаются: после блокировки/снятия роли открытое соединение живёт, истечение `exp` после handshake поток не закрывает. Отлично от APIFE-2 (leak) и APIFE-7 (клиентский reconnect). Плюс основной WS принимает JWT в query-string. | При handshake грузить пользователя+роли из БД; закрывать по `exp`; периодическая перепроверка блокировки/ролей или revocation-события; убрать JWT из query-string. | M |
| PENT-F05 | Unauth resource exhaustion (WS) | `access_control/api/ws_security.py:105-115` | `wss://…/ws/v1/access/security` принимает handshake без токена и висит OPEN (>12с в пробе): `await websocket.receive_json()` без timeout → неаутентифицированные idle-соединения копят worker-connections/память. | `asyncio.wait_for(receive_json(), timeout=5..10)`; проверка `Origin` до `accept()`; nginx `limit_conn`/`limit_req` на WS-handshake; лимит unauth-соединений на IP. | S |
| PENT-F08 ✓ | Clickjacking / transport | `frontend/nginx.conf:7-20` | На `/uk/` HTML и статике нет HSTS/X-Frame-Options/nosniff/Referrer-Policy/Permissions-Policy: server-level `add_header` (строки 7-8) отменяется per-location `add_header` в `location ^~ /assets/` и `location = /index.html` (правило наследования nginx — дочерний блок сбрасывает родительские). CSP есть, но без `frame-ancestors`; домен не в HSTS preload. Заголовки API (middleware) этого не закрывают — это отдельная поверхность фронт-nginx. | Единый security-snippet во *всех* `location` с `always`; `frame-ancestors 'self'`/`'none'`; проверять заголовки раздельно для HTML, JS/CSS и API. | S |
| PENT-F09 | Домен / почта | инфраструктура (`profk.uz` DNS/TLS) | black-box: `www.profk.uz` — CNAME на `profk.uz`, но SAN сертификата только `profk.uz` → TLS name-mismatch; MX `0 profk.uz` при закрытых 25/465/587; SPF и DMARC отсутствуют → домен пригоден для email-spoofing. | Добавить `www` в сертификат+redirect либо снять CNAME; если почта не нужна — null-MX `0 .`, SPF `-all`, DMARC `p=reject`; если нужна — MX/SPF/DKIM/DMARC провайдера. | S |

### Low / Informational

| ID | Категория | Файл:строка / поверхность | Описание | Рекомендация | Объём |
|----|-----------|---------------------------|----------|--------------|:---:|
| PENT-F10 | Права секретов | prod-host `.env` (0644) | `.env` с реальными токенами имеют режим `0644` — читаются другими локальными пользователями ОС (из git/Docker-context корректно исключены). | `chmod 600` всем secret-env на проде; по возможности secret-manager. | S |
| PENT-F11 ✓ | Proxy trust | `uk_management_bot/api/rate_limit_keys.py:51-55` | При пустом `RATE_LIMIT_TRUSTED_PROXIES` `client_ip_key` доверяет `X-Real-IP` без проверки TCP-peer. Внешний nginx перезаписывает заголовок (black-box-обход не удался), но соседний контейнер в общей `uk-network` может напрямую менять rate-bucket. | Задать trusted-proxy allowlist; не публиковать API в общие сети без нужды. | S |
| PENT-F12 | Host-header | edge nginx | Запрос с SNI `profk.uz` и `Host: evil.example` вернул страницу profk.uz (root-redirect использует фиксированный `profk.uz`, poisoning не подтверждён). | Отдельный `default_server` → 421/444; рабочий vhost только `profk.uz` + явный `www`. | S |
| PENT-F13 | DNS/TLS hardening | `profk.uz` | Нет DNSSEC (DS), нет CAA, TLS-сервер без OCSP stapling. | DNSSEC у регистратора, CAA для выбранного CA, OCSP stapling на edge. | S |
| PENT-F14 | Disclosure policy | `/.well-known/security.txt` | Отсутствует (SPA отдаёт HTML 200 вместо 404) → затруднён responsible disclosure, false-positive для сканеров. | RFC 9116 security.txt; неизвестные служебные пути → 404. | S |
| PENT-F15 | Version disclosure | edge nginx :80 | Порт 80 отдаёт `Server: nginx/1.31.2` (HTTPS скрывает). | `server_tokens off` на всех server-block. | S |
| PENT-F16 | Конфликт заголовков | edge/API | Ответы API содержат два HSTS и одновременно `X-Frame-Options: DENY` и `SAMEORIGIN` — политика неоднозначна для старых клиентов. | Назначить edge единственным владельцем заголовков (снимать upstream перед установкой канона). | S |
| PENT-F17 ✓ | Operational | `uk_management_bot/api/routes/health.py` (роутер включён `main.py:136`), но live `…/uk/api/health` → 404 | Health-роут в коде есть и подключён, но на проде `/uk/api/health` и `/uk/api/health/ratelimit` отдают 404 (edge-роутинг/префикс) → мониторинг может не заметить отказ API. | Согласовать edge-путь health с кодом; проверить, что мониторинг реально бьёт живой URL. | S |

**Также подтверждено пентестом как защищённое** (совпадает с фазой 4): только 80/443 наружу, TLS 1.2/1.3, HSTS-redirect, TRACE запрещён, evil-CORS отклонён, `.env`/`.git`/Swagger не раскрыты, source-maps не опубликованы, в прод-JS нет секретов, `alg:none` отклонён, невалидные Telegram Widget/TWA/webhook-подписи отклонены, login-rate-limit после 10 попыток (spoofed `X-Real-IP` не обошёл), защищённые эндпоинты → 401, публичный board-API без утечки PII, upload-proxy проверяет magic-bytes/размер/доступ, RBAC перечитывает роли из БД, cookies HttpOnly/Secure/SameSite=Strict, docs off при `DEBUG=false`, контейнеры от непривилегированных пользователей. Тесты после аудита: backend 104+104, frontend Vitest 324, npm audit 0.

**Ограничение пентеста (фаза 2 не выполнена — нет тестовых аккаунтов):** не проверены authenticated horizontal-IDOR между applicant'ами, executor-scope к назначенным заявкам, границы manager/system_admin, реальные `Set-Cookie`, CSRF на authenticated-мутациях, refresh-concurrency вживую, download чужих файлов, отзыв роли во время живого WS, zone-scoping Access API. Для полноты нужны временные аккаунты applicant A/B + executor + manager и право на помеченные тестовые заявки.

## 4. Top-10 quick wins

| # | Что | Эффект | Объём |
|---|-----|--------|:---:|
| 1 | **CODE-1**: 3 сайта `show_employee_list` → `_return_to_employee_info` | Чинит живой P1-баг менеджерского флоу | S |
| 2 | **APIFE-1 (часть)**: guard active-смены в `/executor/shifts/start` + `.first()` в 3 читателях | Снимает P1: 500-ки карточки сотрудника и TWA | S+ |
| 3 | **CODE-4**: удалить `test_auth_fixes.py` | Убирает пустышку с side-effect на реальную БД из CI | S |
| 4 | **PRAC-1**: канонический `.env.example` + README | Fresh-install снова возможен | S |
| 5 | **APIFE-6**: `extra="forbid"` на PUT-схемы board_config | Закрывает граблю, которая уже стреляла | S |
| 6 | **SEC-NEW-1**: bump aiohttp/ecdsa (или jose→PyJWT) | Чистый pip-audit без 12 ignores | S |
| 7 | **SEC-NEW-3**: guard длины JWT_SECRET | Дешёвая страховка от слабого секрета | S |
| 8 | **APIFE-8**: `invalidateQueries` после PATCH канбана | Доска перестаёт расходиться при мёртвом WS | S |
| 9 | **APIFE-3**: фильтр терминальных статусов в канбан-выборке | Честные счётчики, доска не «теряет» карточки | S |
| 10 | **PRAC-3**: annotated-тег на каждый деплой | Убирает класс проблем «что на проде» | S |

---

## 5. Roadmap рефакторинга (P1 → P2, с учётом зависимостей)

**Волна 0 — пентест «в течение 24 часов» (deploy/infra, до расширения нагрузки):**
PENT-F03 (root_path + proxy-headers + slash-redirect — самый острый: утечка credential-POST в чужой сервис), PENT-F05 (timeout на unauth Access-WS), PENT-F08 (security-заголовки на `/uk/` HTML/JS), PENT-F09 (сертификат `www` / MX-SPF-DMARC), PENT-F10 (`chmod 600` на прод-`.env`), PENT-F17 (health-роутинг для мониторинга). В основном edge-nginx/deploy, не код — но блокируют «безопасно масштабироваться».

**Волна 1 — функциональные баги + дешёвые страховки (1 PR-день):**
CODE-1, APIFE-1, CODE-4, PRAC-1, APIFE-6, SEC-NEW-1 (=PENT-F06), SEC-NEW-3, APIFE-9/10 (попутно). Плюс из пентеста: PENT-F02 (атомарная ротация refresh — вместе с APIFE-14), PENT-F11 (trusted-proxy allowlist), APIFE-12 (=PENT-F07, CSV-escape). Независимы друг от друга.

**Волна 1.5 — least-privilege БД (пентест «в течение недели», High):**
PENT-F01 — сначала ssh-проверить фактическое состояние роли `profk_bot` на обоих продах (демоут superuser мог быть сделан), затем развести миграционную и runtime-роли в `docker-compose.profk.yml` + грант-скриптах. B0-CI-гейт уже доказывает выполнимость — остаётся применить на проде. Требует окна деплоя.

**Волна 2 — согласованность shift-домена (один тематический PR-цикл):**
CODE-3 (единый `utc_now()`, 6 сайтов) → CODE-2 закрывается автоматически → APIFE-4 (validator в схеме) → APIFE-5 (overlap в from-template) → APIFE-11 (`lock=True` в PATCH) → ARCH-7 (проверить гонку планировщик vs дашборд — той же головой, тот же домен). Делать вместе: одна ментальная модель, общие тесты.

**Волна 3 — realtime-контур дашборда:**
APIFE-8 (invalidate — уже в волне 1 как quick win, если не сделан) → APIFE-7 (reconnect + refreshSession) → APIFE-2 (WS-сторож на сервере + дедуп 3 копий хендлера) → PENT-F04 (live-ревалидация ролей/`exp` на WS + убрать JWT из query-string). Порядок важен: клиентский reconnect бессмыслен, пока сервер держит зомби-соединения, и наоборот — чинить парой; PENT-F04 логично лечь тем же касанием ws/router, что APIFE-2.

**Волна 4 — media_service из тени + мёртвый код:**
PRAC-2 (CI-джоба + образ) вместе с PRAC-11 (ruff-scope) — одна задача. Параллельно: DEAD-1/2/4/5 (~700 строк), DEP-1/2, JUNK-1/2/3, PRAC-9/10. DEAD-3 и SEC-NEW-4 — после явного решения владельца по edge-кластеру и `anpr_simulator`.
**Внимание**: возврат media_service в ruff-scope даст ~169 ошибок — сначала ruff-fix, потом гейт.

**Волна 5 — структурный долг (инкрементально, без big-bang):**
ARCH-2 (сервис-слой `api/requests/router.py` — по отработанному образцу shifts) → ARCH-3 (сплит employee_management.py той же механикой block-move; заодно закрывается CODE-8/12 внутри него) → ARCH-4 (AST-гейт на импорты access_control↔ядро — S, сделать рано) → CODE-6 (прокидывание db) → PRAC-5/6 (ratchet mypy + vitest-twa) → ARCH-5/CODE-13 (сужение except в money-path'ах — только при касании).

Плановый hardening из пентеста (PENT-F12/F13/F14/F15/F16 — Host/DNSSEC/CAA/OCSP/security.txt/version/дубли-заголовков) — отдельный edge-nginx-чеклист, не блокирует и делается пачкой при следующем касании конфига edge.

Порядок: волна 0 (пентест-24ч, edge/deploy) и волна 1 (баги) — параллельны и первыми; волна 1.5 (least-privilege БД) — требует окна деплоя. Волны 2–4 взаимонезависимы. Суммарная оценка волн 1–4: ~2–3 недели фонового темпа одного разработчика; волна 5 — постоянный фон «при касании». Волна 0 — в основном конфигурация edge/deploy, счёт на часы, но требует доступа к прод-хосту и InfraSafe-edge.
