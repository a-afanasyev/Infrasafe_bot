# Регистрация жителя: обязательный контакт + каскад двор → дом → квартира в TWA

_Дата: 2026-09-03. Статус: дизайн утверждён владельцем в чате._

## 1. Зачем

Два решения владельца после живой проверки BUG-187:

1. **Без телефона не регистрировать.** И в боте, и в TWA-форме телефон получаем
   только через Telegram-контакт (`request_contact` / `requestContact`), ручной
   ввод номера убираем. Это касается и сотрудника: контакт до ввода токена.
2. **Квартира в TWA выбирается как в боте:** двор → дом → квартира шагами, а не
   одним плоским списком на сотни строк.

Развилка «Я житель / Я сотрудник» на первом входе остаётся. После «Я житель»
житель выбирает путь: бот или TWA-форма. У сотрудника один путь: контакт → токен.

## 2. Факты, на которые опирается дизайн

- `WebAppInitData` пуст для Mini App с reply-кнопки; поэтому Mini App
  открывается только inline web_app-кнопкой (BUG-187, PR #547).
- `Telegram.WebApp.requestContact(cb)` (Bot API 6.9+) показывает системный
  попап; Mini App получает только `status: sent|cancelled`. **Сам контакт
  Telegram доставляет боту обычным сообщением с `contact`** в приватный чат
  пользователя. Значит серверная проверка подписи контакта не нужна: телефон
  сохраняет уже существующий stateless-обработчик бота
  `handlers/phone_share.py:receive_shared_contact` (только свой контакт,
  чужой пересланный отклоняется), а TWA дожидается появления телефона через API.
- Развилка показывается только пока `status=pending`, нет телефона, нет заявок
  на квартиру и роль только `applicant` (`handlers/base.py:_needs_role_choice`).
  Телефон, сохранённый в БД, «закрывает» развилку.
- `POST /api/v2/registration/applicant` сегодня принимает `phone` строкой и
  проверяет только формат, то есть номер можно выдумать.
- `services/addresses/queries.py` уже содержит `list_yards`,
  `list_buildings_for_yard`, `list_apartments_for_building` (только активные).
  Анонимных адресных эндпоинтов нет: все `/api/v2/addresses/*` под ролями.

## 3. Бот

### 3.1 Экран онбординга жителя (`handlers/base.py:_build_onboarding_screen`)

Вызывается из `/start` (когда развилка уже пройдена) и из «Я житель».

| Состояние | Кнопки (reply) |
|---|---|
| нет телефона | `📱 Поделиться контактом` (`request_contact=True`), `📝 Регистрация (форма)` |
| телефон есть, нет одобренной квартиры | `🏠 Выбрать квартиру`, `📝 Регистрация (форма)` |
| профиль полный | клавиатура не нужна (как сейчас) |

Кнопка «📱 Указать телефон» и её текстовый хендлер `start_phone_input`
убираются: контакт запрашивается прямо с экрана. Кнопка формы показывается
только при заданном `FRONTEND_URL` (как сейчас).

### 3.2 Приём контакта жителя

- В `OnboardingStates.waiting_for_phone` из онбординга больше никто не
  попадает; контакт приходит без состояния и обрабатывается
  `phone_share.receive_shared_contact` (`handlers/phone_share.py`, без `state`
  в сигнатуре — так и остаётся). Он сохраняет телефон и **перерисовывает экран
  онбординга** (`_build_onboarding_screen` через уже существующий
  `send_onboarding_screen`, который переезжает из `start_role_choice.py` в
  `handlers/base.py`, чтобы не тянуть импорт роутера развилки): пользователь
  видит «телефон сохранён» и клавиатуру «Выбрать квартиру» / «Регистрация
  (форма)». Выбор квартиры **не автозапускается** — контакт мог прийти из
  TWA (там первый шаг — контакт), и inline-список дворов с FSM-состоянием
  в чате повис бы мёртвым. Цена для бот-пути: одно лишнее нажатие.
  **Гейт перерисовки:** только если `status == "pending"` и роли пользователя
  равны `["applicant"]` (условие `pending` — как у онбординг-ветки `handle_regular_start`, условие ролей — как у `_needs_role_choice`) и
  профиль не полный. Этот же хендлер принимает контакт по запросу менеджера с
  дашборда (`/employees/{id}/request-phone`, `/residents` moderation) —
  сотруднику и одобренному жителю шлём только «телефон сохранён», как сегодня.
- `start_phone_input`, `process_contact`, `process_manual_phone`
  (`handlers/onboarding.py`) удаляются вместе с текстами кнопки «Указать
  телефон» в реестре `button_texts` (`specify_phone`). Локали
  `onboarding.manual_phone_input`, `base.handlers.btn_specify_phone`,
  `onboarding.handlers.btn_specify_phone` больше не используются (оставляем в
  JSON, чистка вне scope).

### 3.3 Гейт выбора квартиры

`start_apartment_selection` (кнопка «Выбрать квартиру») и
`start_apartment_selection_for_profile` (из профиля): если у пользователя нет
телефона — ответ `onboarding.phone_required` с клавиатурой
`request_contact`, выбор не начинается. Текст кнопки шлёт клиент (BUG-169),
поэтому проверка в хендлере, а не по факту наличия кнопки.

### 3.4 Сотрудник (`handlers/start_role_choice.py`)

Факт по коду: `start_role:employee` → `waiting_for_invite_token`; принятый
токен (`handlers/auth.py:start_invite_registration`, вердикт `ok`) только
ставит `waiting_for_full_name`; после ФИО анкета показывает inline
«Подтвердить/Отмена» и ставит `waiting_for_phone`, где `handle_phone_input`
принимает **ручной текстовый** номер (необязательный); строка `users` вместе с
телефоном пишется в `_apply_registration` по колбэку `confirm_position`.

Новое:

- `start_role:employee` → `start_role.employee_contact_prompt` с reply-кнопкой
  `request_contact` + «Отмена» (`buttons.cancel`), состояние
  `RegistrationStates.waiting_for_employee_contact`.
  - Свой контакт → `employee_phone` в FSM-данные (**в БД не пишется**), затем
    `start_role.token_prompt` и `waiting_for_invite_token` как сейчас.
  - Чужой контакт → `phone_request_flow.foreign_contact`, состояние не меняется.
  - Текст: если в `CANCEL_TEXTS` → отмена (текст `auth.registration_cancelled`,
    `state.clear()`, клавиатура снята) — обрабатывается ЗДЕСЬ, потому что
    `start_role_choice_router` стоит в `main.py` раньше `onboarding_router` и
    перехватит текст первым; иначе `start_role.employee_contact_required`,
    состояние не меняется.
- Анкета (`handlers/auth.py`): шаг телефона становится контактным и общим для
  входа через `/join <token>` (там развилки нет): после ФИО, если в FSM нет
  `employee_phone`, бот шлёт `auth.phone_contact_prompt` с `request_contact` и
  ставит `waiting_for_phone`; в этом состоянии принимается только свой
  `F.contact` (→ `employee_phone`, затем экран подтверждения и состояние
  `waiting_for_position_confirmation`, как сегодня); клавиатура контакта несёт
  «Отмена» (`buttons.cancel`): текст из `CANCEL_TEXTS` → `state.clear()` +
  `auth.registration_cancelled`-текст как у `cancel_registration`, любой другой
  текст → `auth.phone_contact_required`. Если `employee_phone` уже есть (путь
  через развилку) — сразу экран подтверждения. `handle_phone_input` (ручной
  ввод) удаляется. Вердикт `applicant_token` по-прежнему чистит состояние
  (теряет `employee_phone`) и показывает экран жителя, который снова попросит
  контакт — это ожидаемо, не дефект.
- `confirm_position` → `_apply_registration(..., phone=data["employee_phone"])`;
  без телефона в FSM колбэк отвечает `auth.phone_contact_required` и не
  регистрирует. Телефон из контакта перезаписывает телефон пред-провиженного
  аккаунта (подтверждён Telegram). При неверном токене повтор ввода токена без
  повторного контакта.

Почему телефон не пишется в БД до подтверждения: иначе сотрудник, бросивший
анкету, на следующем `/start` не увидит развилку (телефон = «выбор сделан») и
уйдёт в онбординг жителя.

### 3.5 Локали бота (ru + uz)

`onboarding.phone_required`, `base.handlers.btn_share_contact` («📱 Поделиться
контактом», reply-кнопка экрана онбординга), `start_role.employee_contact_prompt`,
`start_role.employee_contact_required`, `auth.phone_contact_prompt`,
`auth.phone_contact_required`. Существующий `onboarding.share_contact`
переиспользуется для текста кнопки в FSM-клавиатурах.

### 3.6 Развилка

`_needs_role_choice` не меняется. Тесты фиксируют: свежий пользователь на
`/start` видит развилку; «Я житель» без телефона даёт ровно две кнопки
(контакт, форма); «Я сотрудник» просит контакт, затем токен.

## 4. API (`uk_management_bot/api/registration/`)

### 4.1 Тикет как зависимость

`_ticket_telegram_id` → зависимость `registration_ticket_telegram_id` (Header
`Authorization: Bearer <ticket>`), используется всеми ticket-эндпоинтами.

### 4.2 `POST /start`

Без изменений в проверках. Ответ: поле `apartments` **удаляется**; `prefill`
как сейчас (`phone` из БД). Клиент по `prefill.phone` решает, нужен ли шаг
контакта.

### 4.3 Новые GET под тикетом

| Эндпоинт | Ответ |
|---|---|
| `GET /yards` | `[{id, name}]` активные, по имени |
| `GET /yards/{yard_id}/buildings` | `[{id, address}]` активные; 404 если двор неактивен/нет |
| `GET /buildings/{building_id}/apartments` | `[{id, apartment_number, floor?, entrance?}]` активные, сортировка как в боте (числовая, потом строковая — `sort_key` из `services/address_service/apartments.py:124`, `queries.py` сортирует строкой, повторить); 404 если дом неактивен/нет |
| `GET /contact-status` | `{phone: str \| null}` текущий `users.phone` пользователя тикета |

Читатели: `services/addresses/queries.py` (async, все аргументы keyword-only без
дефолтов): `list_yards(db, include_inactive=False)` → `(yards, counts)`,
`list_buildings_for_yard(db, yard_id=…, include_inactive=False, yard_name=…)` →
кортеж, `list_apartments_for_building(db, building_id=…, include_inactive=False)`;
брать первый элемент. Активность родителя они не проверяют — для 404 нужен
явный `select` двора/дома с `is_active` (маленький хелпер в `catalog.py`).
Сортировка квартир: `sort_key` из `services/address_service/apartments.py:124`. Все под `auth_ratelimit_guard` роутера + `@limiter.limit("60/minute")` (poll
статуса контакта каждые 1.5 с укладывается). Только `is_active` по всей
цепочке (двор, дом, квартира), как в `is_apartment_selectable`.

### 4.4 `POST /applicant`

Схема `RegisterApplicantIn`: **`phone` удаляется**, остаются `full_name`,
`apartment_id`. Телефон берётся из `users.phone` пользователя тикета; если его
нет → `409 {"detail": "Сначала поделитесь контактом в Telegram"}` (код
`phone_required` в detail-строке не нужен, фронт различает по статусу и
тексту как сейчас). `upsert_pending_applicant` получает `phone` из БД
(параметр остаётся, чтобы не трогать сервис).

Пользователь без строки в `users` (никогда не жал `/start`) телефона иметь
не может → тот же 409; на практике Mini App открывается из бота, строка есть.

OpenAPI-снапшот регенерируется из CI-образа.

## 5. TWA (`frontend/src/pages/RegisterPage.tsx` и новые файлы)

### 5.1 Шаги

`loading → contact → yard → building → apartment → confirm → pending`
(плюс `no_telegram`, `already_registered`, `error` как сейчас).

- **contact.** Показывается, если `prefill.phone` пуст. Кнопка «Поделиться
  контактом» → `tg.requestContact(cb)`. При `cb(false)` — подсказка «без
  номера регистрация невозможна», кнопка остаётся. При `cb(true)` — опрос
  `GET /contact-status` каждые 1.5 с до 30 с; как только `phone` пришёл —
  дальше. По таймауту — текст «бот ещё не получил контакт» и кнопка
  «Проверить ещё раз». Если `tg.requestContact` отсутствует (клиент старше
  Bot API 6.9) — текст «обновите Telegram», ручного ввода нет.
- **yard / building / apartment.** Списки крупными кнопками (паттерн
  `twa/pages/inspector/CreatePage.tsx`), сверху хлебные крошки выбранного
  (`Двор › Дом`) и «Назад». Квартиры — сетка кнопок с полем фильтра по номеру
  (клиентский фильтр по подстроке). Пустой список → сообщение и «Назад».
  Двор с единственным домом не пропускается (единообразие с ботом).
- **confirm.** ФИО (prefill из Telegram, редактируемое), телефон (только
  чтение), выбранный адрес одной строкой, «Изменить адрес» (возврат на шаг
  двора), «Отправить». Ошибки сервера показываются как сейчас; 401 →
  повторный `start()` и просьба отправить ещё раз.

### 5.2 Код

- `hooks/useRegistration.ts`: `start()` без `apartments`; `submit(ticket,
  {full_name, apartment_id})`; новые `yards(ticket)`, `buildings(ticket, yardId)`,
  `apartments(ticket, buildingId)`, `contactStatus(ticket)` на том же «голом»
  axios. Типы там же.
- `pages/register/ContactStep.tsx`, `pages/register/AddressCascade.tsx`
  (три уровня + крошки + фильтр), `pages/register/ConfirmStep.tsx`;
  `RegisterPage.tsx` — только машина шагов.
- `twa/hooks/useTelegramSDK.ts`: в тип `TelegramWebApp` добавляется
  `requestContact?: (cb: (sent: boolean) => void) => void`.
- Локали фронта `register.*`: `contact_title`, `contact_hint`, `share_contact`,
  `contact_declined`, `contact_waiting`, `contact_timeout`, `contact_retry`,
  `update_telegram`, `select_yard`, `select_building`, `select_apartment`,
  `filter_apartment`, `no_items`, `back`, `change_address`, `phone_required`.

## 6. Тесты

- **Бот** (`uk_management_bot/tests/`): экран онбординга без телефона = контакт +
  форма, с телефоном = квартира + форма; гейт `start_apartment_selection` и
  профильного входа без телефона; `receive_shared_contact` перерисовывает экран
  онбординга и не ставит FSM-состояние; сотрудник: текст без контакта отклонён,
  «Отмена» работает, контакт → запрос токена, `/join`-анкета просит контакт и
  отклоняет текст, `confirm_position` без телефона отказывает, с телефоном
  пишет `users.phone`; роутинг контакта в каждом состоянии по порядку `main.py`
  (`routing_probe.resolve_ctx`, observer `message`).
- **API** (`uk_management_bot/tests/registration/`, набор 1; `tests/api/test_registration_full_name_validation.py` — набор 2, обновить под схему без `phone`): три адресных GET и `contact-status` с тикетом
  и без (401); неактивный двор/дом → 404; `applicant` без телефона в БД → 409,
  с телефоном → 200 и телефон взят из БД; `start` без `apartments`.
- **Фронт** (vitest): шаг контакта (нет `requestContact` → «обновите»,
  `cb(false)` → подсказка, `cb(true)` + poll → переход), каскад (выбор
  двора грузит дома, «Назад», фильтр квартир), confirm отправляет
  `{full_name, apartment_id}`, пропуск шага контакта при `prefill.phone`.
- Ломаются и обновляются существующие: `uk_management_bot/tests/registration/test_registration_start.py`
  (`body["apartments"]`), `frontend/src/pages/RegisterPage.test.tsx`
  (мок `apartments`/`phone`), `tests/api/test_registration_full_name_validation.py`,
  `uk_management_bot/tests/test_base_register_button.py`, `tests/handlers/test_start_role_choice.py`,
  тесты онбординга с «Указать телефон» (найти по `SPECIFY_PHONE_TEXTS`/`btn_specify_phone`).
- Эталон: `make test-ci`, OpenAPI-снапшот из CI-образа.

## 7. Раскатка

api, app и фронт на profk и 105 (фронт — отдельный шаг деплоя). Миграций нет.
Теги по процедуре. Проверка владельцем: `/start` свежим аккаунтом → развилка →
«Я житель» → контакт → квартира; TWA-форма: контакт → каскад → заявка.

## 8. Вне scope

- Пагинация списков квартир в боте (сегодня плоский список до 500).
- Наблюдение: после отправки формы 2026-09-03 10:59 ФИО тестового аккаунта в
  БД осталось «Infrasafe manager». Проверить отдельно, вероятно, `/start`
  перезаписывает имена из профиля Telegram.
