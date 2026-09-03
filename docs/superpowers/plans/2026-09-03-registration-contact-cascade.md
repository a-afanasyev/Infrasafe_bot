# Регистрация: обязательный контакт + каскад адреса в TWA — план реализации

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Телефон только из Telegram-контакта (бот и TWA, житель и сотрудник); в TWA-форме квартира выбирается каскадом двор → дом → квартира.

**Architecture:** Контакт из `requestContact` Mini App приходит боту сообщением; stateless-хендлер `phone_share` сохраняет `users.phone`, TWA опрашивает `GET /registration/contact-status`. Каскад — три GET под тикетом регистрации поверх `services/addresses/queries.py`. В боте экран онбординга без телефона показывает только кнопку контакта и форму; сотрудник даёт контакт до токена (телефон в FSM до `confirm_position`).

**Tech Stack:** aiogram 3, FastAPI + SQLAlchemy async, React + vitest, i18next. Спека: `docs/superpowers/specs/2026-09-03-registration-contact-cascade-design.md`.

**Правила:** TDD (RED → GREEN), `PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider <file>` для быстрой петли; `settings` в тестах патчить через модуль-потребитель; эталон — `make test-ci`; OpenAPI-снапшот регенерировать из CI-образа. Коммит после каждой задачи.

---

## Структура файлов

**Бот**
- Modify `uk_management_bot/handlers/base.py` — `_build_onboarding_screen` (контакт вместо «Указать телефон», «Выбрать квартиру» только с телефоном), `send_onboarding_screen` переезжает сюда из `start_role_choice.py`.
- Modify `uk_management_bot/handlers/phone_share.py` — после сохранения перерисовка экрана онбординга под гейтом pending+applicant.
- Modify `uk_management_bot/handlers/onboarding.py` — удалить `start_phone_input`, `process_contact`, `process_manual_phone`, `SPECIFY_PHONE_TEXTS`.
- Modify `uk_management_bot/handlers/user_apartment_selection.py` — гейт по телефону в `start_apartment_selection` и `start_apartment_selection_for_profile`; loader `_load_phone(db, telegram_id)`.
- Modify `uk_management_bot/handlers/start_role_choice.py` — состояние `waiting_for_employee_contact`, хендлеры контакта/текста, `send_onboarding_screen` импортируется из `base`.
- Modify `uk_management_bot/handlers/auth.py` — контактный шаг вместо `handle_phone_input`; `confirm_position` берёт `employee_phone`.
- Modify `uk_management_bot/states/registration.py` — `waiting_for_employee_contact`.
- Modify `uk_management_bot/utils/button_texts.py` — убрать `specify_phone`.
- Modify `uk_management_bot/config/locales/{ru,uz}.json` — ключи §3.5 спеки.
- New `uk_management_bot/keyboards/contact.py` — `get_share_contact_keyboard(language, with_cancel: bool)` (одна точка сборки reply-клавиатуры `request_contact`).
- Tests: `uk_management_bot/tests/test_onboarding_contact_gate.py` (new), `tests/handlers/test_start_role_choice.py`, `tests/handlers/test_employee_contact_step.py` (new), `tests/test_base_register_button.py`, `tests/handlers/test_phone_share.py`.

**API**
- Modify `uk_management_bot/api/registration/router.py` — зависимость тикета, `/start` без `apartments`, новые GET, `/applicant` без `phone`.
- Modify `uk_management_bot/api/registration/schemas.py` — `YardOut`, `BuildingOut`, `ApartmentOut` (id, apartment_number, floor, entrance), `ContactStatusOut`; убрать `phone` и `apartments`.
- Modify `uk_management_bot/api/registration/catalog.py` — `list_yards_out`, `list_buildings_out(yard_id)`, `list_apartments_out(building_id)` с 404-семантикой (возврат `None` при неактивном/отсутствующем родителе), `sort_key`.
- Tests: `uk_management_bot/tests/registration/test_registration_cascade.py` (new), `test_registration_start.py`, `test_registration_applicant.py`, `tests/api/test_registration_full_name_validation.py`.
- Snapshot: `docs/api/openapi.json` (или где лежит снапшот — см. `scripts/` / CI job) — регенерировать из CI-образа.

**Фронт**
- Modify `frontend/src/hooks/useRegistration.ts` — новые методы и типы.
- Modify `frontend/src/twa/hooks/useTelegramSDK.ts` — `requestContact?` в типе.
- New `frontend/src/pages/register/ContactStep.tsx`, `AddressCascade.tsx`, `ConfirmStep.tsx`, `useContactPolling.ts`.
- Modify `frontend/src/pages/RegisterPage.tsx` — машина шагов.
- Modify `frontend/src/i18n/locales/{ru,uz}.json` — `register.*` ключи §5.2.
- Tests: `frontend/src/pages/RegisterPage.test.tsx`, `frontend/src/pages/register/AddressCascade.test.tsx`, `ContactStep.test.tsx`.

---

## Часть A — бот

### Task A1: клавиатура контакта + экран онбординга

**Files:** New `keyboards/contact.py`; Modify `handlers/base.py:400-433`; Modify `utils/button_texts.py`; locales; Test `tests/test_base_register_button.py`, New `tests/test_onboarding_contact_gate.py`.

- [ ] **RED.** В `test_onboarding_contact_gate.py`: (1) `_build_onboarding_screen(ctx(phone=None), "ru")` → reply-кнопки ровно `[btn_share_contact(request_contact=True)], [btn_register_webapp]`, без `btn_select_apartment`; (2) `ctx(phone="+998…", has_approved_apartment=False)` → `[btn_select_apartment], [btn_register_webapp]`, без контакта; (3) `FRONTEND_URL=""` → без формы. `ctx` — `_MenuContext(status="pending", phone=…, has_approved_apartment=False, has_any_apartment=False, db_roles=["applicant"], active_role="applicant")`.
- [ ] Run → FAIL (сейчас есть «Указать телефон»).
- [ ] **GREEN.** `keyboards/contact.py`:
  ```python
  def get_share_contact_keyboard(language: str, *, with_cancel: bool) -> ReplyKeyboardMarkup:
      rows = [[KeyboardButton(text=get_text("onboarding.share_contact", language=language), request_contact=True)]]
      if with_cancel:
          rows.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])
      return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)
  ```
  В `_build_onboarding_screen`: если `not ctx.phone` → строка `KeyboardButton(text=get_text("base.handlers.btn_share_contact"), request_contact=True)`; иначе если `not ctx.has_approved_apartment` → `btn_select_apartment`; затем форма. Локали: `base.handlers.btn_share_contact` ru «📱 Поделиться контактом» / uz «📱 Kontaktni ulashish»; `onboarding.phone_required` ru «Сначала поделитесь контактом — нажмите кнопку ниже.» / uz «Avval kontaktni ulashing — quyidagi tugmani bosing.». `button_texts.py`: удалить `specify_phone` запись и `get_specify_phone_texts`.
- [ ] Обновить `test_base_register_button.py` (ожидания кнопок) и `tests/handlers/test_start_role_choice.py::test_resident_shows_existing_onboarding_screen` (две кнопки: контакт + форма).
- [ ] Run оба файла → PASS. Commit `feat(bot): экран онбординга — контакт вместо ручного телефона`.

### Task A2: удалить ручной ввод телефона в онбординге

**Files:** Modify `handlers/onboarding.py:78,167-293`; tests, ссылающиеся на `SPECIFY_PHONE_TEXTS`/`start_phone_input`/`process_manual_phone` (`grep -rn` по `uk_management_bot/tests`).

- [ ] **RED.** В `test_onboarding_contact_gate.py`: `from uk_management_bot.handlers import onboarding; assert not hasattr(onboarding, "process_manual_phone")` и роутинг: `resolve_ctx(MAIN, make_message("+998901234567"), "message", raw_state="OnboardingStates:waiting_for_phone", roles=["applicant"], user=None)` не равен `("…onboarding", "process_manual_phone")`.
- [ ] Run → FAIL.
- [ ] **GREEN.** Удалить три хендлера и константу; удалить `SPECIFY_PHONE_TEXTS` из списка системных текстов внутри `process_manual_phone` (сам хендлер уходит). Удалить/переписать старые тесты этих хендлеров.
- [ ] Run `pytest uk_management_bot/tests -q -k "onboarding or phone"` → PASS. Commit `refactor(bot): убрать ручной ввод телефона в онбординге`.

### Task A3: stateless-контакт перерисовывает экран онбординга

**Files:** Modify `handlers/base.py` (переезд `send_onboarding_screen` + новый loader `_load_onboarding_redraw(db, telegram_id) -> _MenuContext | None`); Modify `handlers/phone_share.py`; Modify `handlers/start_role_choice.py` (импорт из base); Test `tests/handlers/test_phone_share.py`.

- [ ] **RED.** В `test_phone_share.py`: (1) pending applicant без квартиры → после контакта `message.answer` вызван дважды: «телефон сохранён» и экран онбординга с reply-кнопкой `btn_select_apartment`; (2) пользователь с ролью `executor`/status approved → только «телефон сохранён» (один вызов, `ReplyKeyboardRemove`); (3) FSM не трогается (`state` не передаётся).
- [ ] Run → FAIL.
- [ ] **GREEN.** После `saved`: `ctx = await run_db(lambda s: _load_onboarding_redraw(s, tg_id), db=_db)`; если `ctx and ctx.status == "pending" and (ctx.db_roles or ["applicant"]) == ["applicant"] and not (ctx.phone and ctx.has_approved_apartment)` → `text, kb = _build_onboarding_screen(ctx, lang)`; `await message.answer(text, reply_markup=kb)`. Перенести `send_onboarding_screen` в `base.py`, в `start_role_choice.py` импортировать.
- [ ] Run → PASS. Commit `feat(bot): контакт вне FSM перерисовывает экран онбординга`.

### Task A4: гейт выбора квартиры по телефону

**Files:** Modify `handlers/user_apartment_selection.py:243-262, 630-660`; Test `tests/test_onboarding_contact_gate.py`.

- [ ] **RED.** `start_apartment_selection(msg, state, language="ru", _db=db)` с пользователем без телефона → `msg.answer` с `onboarding.phone_required` и `reply_markup` = клавиатура контакта (`request_contact=True`), `state.set_state` не вызван; профильный вариант — `callback.message.answer` аналогично.
- [ ] Run → FAIL.
- [ ] **GREEN.** Loader `_load_user_phone(db, telegram_id) -> Optional[str]`; в обоих входах перед загрузкой дворов: `if not phone: answer(...); return`.
- [ ] Run → PASS. Commit `feat(bot): выбор квартиры только после контакта`.

### Task A5: сотрудник — контакт до токена

**Files:** Modify `states/registration.py`; Modify `handlers/start_role_choice.py:88-105`; locales (`start_role.employee_contact_prompt`, `start_role.employee_contact_required`); New `tests/handlers/test_employee_contact_step.py`.

- [ ] **RED.** (1) `choose_employee` → `state.set_state(waiting_for_employee_contact)`, ответ с клавиатурой `request_contact` + cancel; (2) свой контакт в этом состоянии → `state.update_data(employee_phone="+998…")`, `set_state(waiting_for_invite_token)`, текст `start_role.token_prompt`; (3) чужой контакт → `phone_request_flow.foreign_contact`, состояние не меняется; (4) текст «abc» → `employee_contact_required`; (5) текст из `CANCEL_TEXTS` → `state.clear()` + `auth.registration_cancelled`; (6) роутинг: `resolve_ctx(MAIN, make_message(text), "message", raw_state="RegistrationStates:waiting_for_employee_contact", roles=["applicant"], user=None)` → `("…start_role_choice", "employee_contact_text")`, и контакт (сделать `Message` с `contact=Contact(...)`) → `("…start_role_choice", "employee_contact")`.
- [ ] Run → FAIL.
- [ ] **GREEN.** Хендлеры `employee_contact` (`StateFilter(waiting_for_employee_contact), F.contact`) и `employee_contact_text` (`StateFilter(waiting_for_employee_contact)`), клавиатура из `keyboards/contact.py` с cancel.
- [ ] Run → PASS. Commit `feat(bot): сотрудник делится контактом до ввода токена`.

### Task A6: анкета сотрудника — контакт вместо ручного телефона

**Files:** Modify `handlers/auth.py:375-600`; locales (`auth.phone_contact_prompt`, `auth.phone_contact_required`); Test `tests/handlers/test_employee_contact_step.py` (продолжение) + существующие тесты auth (`grep -rn handle_phone_input uk_management_bot/tests`).

- [ ] **RED.** (1) `handle_full_name_input` при `employee_phone` в FSM → экран подтверждения и `waiting_for_position_confirmation`; без него → `auth.phone_contact_prompt` с клавиатурой контакта + cancel и `waiting_for_phone`; (2) в `waiting_for_phone` свой контакт → `employee_phone`, экран подтверждения; текст «+99890…» → `phone_contact_required`; cancel → `state.clear()`; (3) `handle_position_confirmation` без `employee_phone` → `auth.phone_contact_required`, `_apply_registration` не вызван; с ним → вызван с `phone="+998…"`.
- [ ] Run → FAIL.
- [ ] **GREEN.** Заменить `handle_phone_input` на `handle_phone_contact` (`F.contact`) + `handle_phone_text`; читать `employee_phone` везде вместо `phone`.
- [ ] Run `pytest uk_management_bot/tests -q -k "auth or invite or employee"` → PASS. Commit `feat(bot): анкета сотрудника принимает телефон только контактом`.

### Task A7: развилка — регрессионные тесты + прогон набора бота

- [ ] Дополнить `tests/handlers/test_start_role_choice.py`: свежий пользователь на `/start` видит развилку (уже есть — проверить), «Я житель» → две кнопки, «Я сотрудник» → контакт.
- [ ] `PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider uk_management_bot/tests` → все зелёные (известные локальные красные сверить с чистым main).
- [ ] Commit `test(bot): развилка и контактные шаги`.

## Часть B — API

### Task B1: зависимость тикета + `/contact-status`

**Files:** Modify `api/registration/router.py`, `schemas.py`; New `tests/registration/test_registration_cascade.py`.

- [ ] **RED.** `GET /api/v2/registration/contact-status` без заголовка → 401; с тикетом пользователя без строки → `{"phone": null}`; с `seed_user(phone="+998…")` → `{"phone": "+998…"}`.
- [ ] Run → FAIL (404).
- [ ] **GREEN.** `async def registration_ticket_telegram_id(authorization: str | None = Header(default=None)) -> int` (тело `_ticket_telegram_id`); `ContactStatusOut(phone: str | None)`; эндпоинт `@limiter.limit("60/minute")`.
- [ ] Run → PASS. Commit `feat(api): registration contact-status + ticket dependency`.

### Task B2: каскад адресов под тикетом

**Files:** Modify `catalog.py`, `router.py`, `schemas.py`; Test `test_registration_cascade.py`.

- [ ] **RED.** С `seed_apartment()`: `GET /yards` → `[{id, name}]` только активные; `GET /yards/{id}/buildings` → `[{id, address}]`; неактивный/несуществующий двор → 404; `GET /buildings/{id}/apartments` → `[{id, apartment_number, floor, entrance}]`, сортировка `["2","10","10а"]` → числовая; неактивный дом → 404; все три без тикета → 401.
- [ ] Run → FAIL.
- [ ] **GREEN.** `catalog.py`: `list_yards_out(db)`, `list_buildings_out(db, yard_id) -> list | None` (None = двор нет/неактивен), `list_apartments_out(db, building_id) -> list | None` (проверка дома и его двора), `sort_key` как в `address_service/apartments.py:124`. Роутер: три GET, `@limiter.limit("60/minute")`, 404 при `None`.
- [ ] Run → PASS. Commit `feat(api): каскад двор/дом/квартира для регистрации`.

### Task B3: `/start` без `apartments`, `/applicant` без `phone`

**Files:** Modify `router.py`, `schemas.py`, `catalog.py` (удалить `list_apartments`); Tests `test_registration_start.py`, `test_registration_applicant.py`, `tests/api/test_registration_full_name_validation.py`.

- [ ] **RED.** `/start` → в теле нет `apartments`; `/applicant` с телом `{full_name, apartment_id}` и пользователем без телефона → 409 detail «Сначала поделитесь контактом в Telegram»; с телефоном в БД → 200 и `users.phone` не изменился; тело с `phone` → игнорируется/422 (extra=forbid не включаем, просто не читаем).
- [ ] Run → FAIL.
- [ ] **GREEN.** Схемы; в роутере телефон из `get_user_by_telegram_id`; `upsert_pending_applicant(..., phone=existing.phone)`.
- [ ] Run `pytest uk_management_bot/tests/registration tests/api/test_registration_full_name_validation.py` → PASS. Commit `feat(api): телефон регистрации только из подтверждённого контакта`.

### Task B4: OpenAPI-снапшот

- [ ] Найти скрипт регенерации (`grep -rn openapi Makefile scripts .github/workflows`), запустить из образа `uk-app:ci-local` (см. память: локальный pydantic отличается). Commit `chore(api): openapi snapshot`.

## Часть C — фронт

### Task C1: типы и хук

**Files:** Modify `frontend/src/hooks/useRegistration.ts`, `frontend/src/twa/hooks/useTelegramSDK.ts`.

- [ ] **RED.** `frontend/src/hooks/useRegistration.test.ts`: мок axios; `yards('t')` → GET `/api/v2/registration/yards` с Bearer; `buildings('t', 3)`, `apartments('t', 5)`, `contactStatus('t')`; `submit('t', {full_name, apartment_id})` — тело без `phone`.
- [ ] Run `cd frontend && npx vitest run src/hooks/useRegistration.test.ts` → FAIL.
- [ ] **GREEN.** Методы + типы `RegistrationYard{id,name}`, `RegistrationBuilding{id,address}`, `RegistrationApartment{id,apartment_number,floor?,entrance?}`; `RegistrationStart` без `apartments`. В `TelegramWebApp`: `requestContact?: (cb: (sent: boolean) => void) => void`.
- [ ] Run → PASS. Commit `feat(frontend): registration API client for cascade + contact`.

### Task C2: ContactStep + polling

**Files:** New `pages/register/useContactPolling.ts`, `pages/register/ContactStep.tsx`; i18n; Test `pages/register/ContactStep.test.tsx`.

- [ ] **RED.** (1) без `requestContact` в SDK → текст `register.update_telegram`, кнопки нет; (2) `requestContact(cb)` → `cb(false)` → `register.contact_declined`, кнопка остаётся; (3) `cb(true)` → polling `contactStatus` каждые 1500 мс (fake timers), первый ответ `{phone:null}`, второй `{phone:"+998…"}` → `onDone("+998…")`; (4) 30 с без телефона → `register.contact_timeout` + кнопка `register.contact_retry`.
- [ ] Run → FAIL.
- [ ] **GREEN.** Пропсы `{ticket, contactStatus, onDone}`; SDK через `useTelegramSDK().tg`.
- [ ] Run → PASS. Commit `feat(frontend): registration contact step via requestContact`.

### Task C3: AddressCascade

**Files:** New `pages/register/AddressCascade.tsx`; i18n; Test `AddressCascade.test.tsx`.

- [ ] **RED.** Пропсы `{ticket, api:{yards,buildings,apartments}, onSelect(apartment, labels)}`: рендер дворов; клик → загрузка домов и крошка «Двор»; «Назад» возвращает; клик дома → квартиры сеткой; фильтр по «10» оставляет «10», «100», «101»; клик квартиры → `onSelect({id…}, {yard, building})`; пустой список → `register.no_items`.
- [ ] Run → FAIL.
- [ ] **GREEN.** Паттерн кнопок из `twa/pages/inspector/CreatePage.tsx:172-196`; квартиры — `grid grid-cols-4 gap-2`; фильтр `Input`.
- [ ] Run → PASS. Commit `feat(frontend): yard/building/apartment cascade for registration`.

### Task C4: RegisterPage — машина шагов + ConfirmStep

**Files:** New `pages/register/ConfirmStep.tsx`; Modify `pages/RegisterPage.tsx`; Test `pages/RegisterPage.test.tsx` (переписать).

- [ ] **RED.** (1) `start()` с `prefill.phone` → сразу шаг двора (мок каскада); без телефона → ContactStep; (2) после выбора квартиры → ConfirmStep с ФИО (prefill), телефоном (read-only), адресом; «Изменить адрес» → шаг двора; (3) submit → `submit('ticket-1', {full_name, apartment_id})` → `pending`; (4) 409 «уже» → already_registered; (5) 401 при submit → повторный `start()` и ошибка «отправьте ещё раз».
- [ ] Run → FAIL.
- [ ] **GREEN.** Фазы `loading | no_telegram | contact | address | confirm | pending | already_registered`.
- [ ] Run `npx vitest run src/pages` → PASS; `npm test` целиком → зелёный; `npx tsc --noEmit`. Commit `feat(frontend): пошаговая регистрация жителя`.

## Часть D — интеграция и раскатка

### Task D1: эталон
- [ ] `make test-ci` → зелёный (при «postgres не поднялся» — повтор).
- [ ] `cd frontend && npm test && npm run build` → зелёные.

### Task D2: документация
- [ ] `docs/bugs-2026-09-03.md` — короткая запись; `docs/tech/` при наличии описания регистрации — обновить (grep «registration/start»).

### Task D3: PR, мерж, раскатка
- [ ] Push, PR (тело по шаблону, ссылка на спеку), CI зелёный, мерж.
- [ ] profk и 105: skill `uk-deploy` — build api access-api app migrate → migrate → up api, access-api, app; фронт — отдельный шаг (см. память `reference_prod_deploy_env`). Инлайн `ssh host '…'`.
- [ ] Теги `scripts/tag-deploy.sh profk --push`, `infrasafe --push`.
- [ ] Проверка владельцем: свежий аккаунт → развилка → «Я житель» → контакт → квартира; TWA-форма: контакт → каскад → заявка; «Я сотрудник» → контакт → токен.
