# BUG-188: документы жителя — фото и файлы вне состояния теряются — план починки

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** житель всегда может отправить документ боту: после менеджерского запроса, на экране выбора типа и просто «из ниоткуда» — ни одно фото/файл не пропадает молча.

**Architecture:** приём файлов остаётся в существующем FSM (`OnboardingStates.waiting_for_document_type → waiting_for_document_file → waiting_for_document_confirmation`, `handlers/onboarding.py`). Добавляются три входа в него: inline-кнопка в уведомлении о запросе документов, stateless-ловушка фото/файлов в приватном чате и «мягкий» ответ на фото на экране выбора типа. Ничего в хранении (Telegram `file_id` + `user_documents` + копия в Media Service) не меняется. TWA — вне scope.

**Tech Stack:** aiogram 3, pytest + `tests/handlers/routing_probe.resolve_ctx`. Быстрая петля: `PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider <file>`; эталон `make test-ci`.

---

## Диагноз (факты, проверено 2026-09-03)

| # | Путь | Что происходит | Где |
|---|------|----------------|-----|
| 1 | Менеджер «Запросить документы» → житель шлёт фото | Жителю уходит **только текст** без кнопки и без состояния (`services/notification_service/documents.py:53`, `handlers/user_management/fsm.py:454-463` через `send_to_user`, который не умеет `reply_markup`). Фото вне FSM **не ловит никто** (`resolve_ctx` → `None`), тишина. | `fsm.py`, `channel.py:45` |
| 2 | Онбординг: экран выбора типа → житель сразу шлёт фото | Хендлер `process_document_type_selection` фильтрует `F.text` — фото пропадает молча (`resolve_ctx` в `waiting_for_document_type` → `None`). | `onboarding.py:199` |
| 3 | Reply-кнопка «Загрузить документы» | Генератор кнопки мёртв (комментарий `onboarding.py:183`), хендлер `start_document_upload` живой, но извне недостижим. | `onboarding.py:186` |

Фото в `waiting_for_document_file` работает (`process_document_file` берёт `message.photo[-1]`).

## Структура файлов

- Modify `uk_management_bot/services/notification_service/channel.py` — `send_to_user(bot, tid, text, reply_markup=None)`.
- Modify `uk_management_bot/handlers/user_management/fsm.py:454-463` — передать inline-клавиатуру «📤 Загрузить документы».
- New `uk_management_bot/keyboards/documents_entry.py` — `get_upload_documents_inline(language)` (одна кнопка, callback `docs:upload`).
- Modify `uk_management_bot/handlers/onboarding.py` — (a) колбэк `docs:upload` → выбор типа; (b) stateless-ловушка `F.photo | F.document` в приватном чате; (c) фото/файл в `waiting_for_document_type` → подсказка + клавиатура типов; (d) `start_document_upload` разбить на `_begin_document_type_step(message_or_cb.message, state, lang)` для повторного использования.
- Modify `uk_management_bot/config/locales/{ru,uz}.json` — `onboarding.documents.btn_upload_inline`, `onboarding.documents.send_after_button`, `onboarding.documents.choose_type_first`.
- Modify `uk_management_bot/main.py` — **не нужно** (все хендлеры в `onboarding_router`, он уже подключён).
- Test: New `uk_management_bot/tests/handlers/test_bug188_document_entry.py`; Modify `tests/handlers/test_bug_p2_nav_ux.py` при необходимости.

## Решения, которые план принимает сам (сказать владельцу в отчёте)

- Stateless-ловушка отвечает **всем** пользователям приватного чата, кроме тех, у кого висит другое FSM-состояние (ловушка под `StateFilter(None)`). Сотрудник, приславший фото вне сценария, тоже получит подсказку «чтобы загрузить документ — нажмите кнопку» — это лучше тишины, а сценариев, где фото вне состояния было бы штатным, в боте нет (все `F.photo`-хендлеры привязаны к состояниям, см. инвентарь в диагнозе).
- Житель с `verification_status == 'requested'` по кнопке сразу попадает в выбор типа; запрошенные менеджером типы в этой итерации **не подсвечиваются** (YAGNI — клавиатура и так из пяти кнопок).
- После сохранения документа менеджеру отдельное уведомление **не шлём** (как сегодня): документы видны в карточке жителя. Если владелец захочет — отдельный пункт.

---

### Task 1: `send_to_user` с клавиатурой + кнопка в уведомлении о запросе

**Files:** Modify `services/notification_service/channel.py:45`; New `keyboards/documents_entry.py`; Modify `handlers/user_management/fsm.py:454-463`; locales; Test `tests/handlers/test_bug188_document_entry.py`.

- [ ] **RED.** (1) `send_to_user(bot, 1, "t", reply_markup=kb)` зовёт `bot.send_message(1, "t", reply_markup=kb, request_timeout=…)`; без аргумента — как раньше (совместимость с существующими тестами `send_to_user`). (2) `get_upload_documents_inline("ru")` → одна кнопка с текстом `onboarding.documents.btn_upload_inline` и `callback_data == "docs:upload"`. (3) `process_document_request` (fsm.py, хендлер `UserManagementStates.waiting_for_document_request`) при успешном запросе зовёт `send_to_user` с `reply_markup` — inline-клавиатурой из (2). Мокать `run_db` → `_DocumentRequest(success=True, target_telegram_id=5, user_text="t", channel_text="c")`, патчить `uk_management_bot.services.notification_service.send_to_user`.
- [ ] Run → FAIL.
- [ ] **GREEN.** `send_to_user(..., reply_markup=None)` пробрасывает `reply_markup` только если не `None`. Клавиатура: `InlineKeyboardMarkup([[InlineKeyboardButton(text=get_text("onboarding.documents.btn_upload_inline"), callback_data="docs:upload")]])`. В fsm.py: `await send_to_user(bot, tid, requested.user_text, reply_markup=get_upload_documents_inline(user_lang))` — язык жителя: `_DocumentRequest` расширить полем `target_language` (из `target_user.language` в юните `_apply_document_request`, дефолт "ru"). Локали ru: `btn_upload_inline` «📤 Загрузить документы»; uz «📤 Hujjatlarni yuklash».
- [ ] Run → PASS. Существующие тесты `fsm.py`/`notification_service` — зелёные. Commit `feat(bot): кнопка «Загрузить документы» в уведомлении о запросе документов (BUG-188)`.

### Task 2: колбэк `docs:upload` → выбор типа документа

**Files:** Modify `handlers/onboarding.py` (рядом с `start_document_upload`); Test тот же файл.

- [ ] **RED.** (1) `open_document_upload(callback, state, language="ru")`: `callback.message.answer` с текстом `onboarding.documents.title + description` и `reply_markup` = `get_document_type_keyboard`, `state.set_state(waiting_for_document_type)`, `callback.answer()` вызван, inline-разметка снята (`edit_reply_markup(reply_markup=None)` в try). (2) Роутинг: `resolve_ctx(MAIN, make_callback("docs:upload"), "callback_query", roles=["applicant"], user=None)` → `("…onboarding", "open_document_upload")` — и с `raw_state=None`, и с висящим `OnboardingStates:waiting_for_document_type` (повторное нажатие не ломает).
- [ ] Run → FAIL.
- [ ] **GREEN.** Вынести тело `start_document_upload` в `async def _begin_document_type_step(target: Message, state, lang)`; `start_document_upload` и новый `@router.callback_query(F.data == "docs:upload") open_document_upload` зовут его. Порядок в `main.py`: `onboarding_router` (311) — до него колбэки `docs:*` никто не перехватывает (проверить: `grep -rn '"docs' handlers` → пусто).
- [ ] Run → PASS. Commit `feat(bot): docs:upload — вход в загрузку документов по inline-кнопке`.

### Task 3: stateless фото/файл в приватном чате → подсказка с кнопкой

**Files:** Modify `handlers/onboarding.py`; locales; Test тот же файл.

- [ ] **RED.** (1) `catch_stray_document(message, language="ru")` для `message.photo` и для `message.document` отвечает `onboarding.documents.send_after_button` с `reply_markup=get_upload_documents_inline`. (2) Роутинг по порядку `main.py`: фото без состояния (`raw_state=None`, private chat) → `("…onboarding", "catch_stray_document")`; фото в `FeedbackStates:waiting_for_photo` → по-прежнему `("…feedback", …)`; фото в `RequestStates:media` → `("…requests.create", …)`; фото в `ExecutorRequestStates:waiting_completion_media` → `("…requests.executor", …)`; фото в `OnboardingStates:waiting_for_document_file` → `process_document_file`. (3) Группа (`chat.type == "supergroup"`) без состояния → `None` (ловушка только для private).
- [ ] Run → FAIL.
- [ ] **GREEN.** `@router.message(StateFilter(None), F.chat.type == "private", F.photo | F.document) async def catch_stray_document(...)`. Локали: `send_after_button` ru «Чтобы загрузить документ, нажмите кнопку ниже и выберите его тип.» / uz «Hujjat yuklash uchun quyidagi tugmani bosing va turini tanlang.».
- [ ] Run → PASS (включая `tests/handlers/test_role_gate_routing.py`, `test_bug155_filter_overlap.py`). Commit `fix(bot): фото/файл вне сценария больше не теряются — подсказка с кнопкой (BUG-188)`.

### Task 4: фото на экране выбора типа

**Files:** Modify `handlers/onboarding.py`; locales; Test тот же файл.

- [ ] **RED.** `resolve_ctx(MAIN, photo, "message", raw_state="OnboardingStates:waiting_for_document_type", …)` → `("…onboarding", "document_before_type")`; хендлер отвечает `onboarding.documents.choose_type_first` с `reply_markup=get_document_type_keyboard`, состояние не меняется.
- [ ] Run → FAIL.
- [ ] **GREEN.** `@router.message(OnboardingStates.waiting_for_document_type, F.photo | F.document) async def document_before_type(...)`. Локали: ru «Сначала выберите тип документа кнопкой ниже, затем отправьте файл ещё раз.» / uz «Avval quyidagi tugma bilan hujjat turini tanlang, so‘ng faylni qayta yuboring.».
- [ ] Run → PASS. Commit `fix(bot): фото до выбора типа документа — подсказка вместо тишины`.

### Task 5: эталон, документация, раскатка

- [ ] `PYTHONPATH=. .venv/bin/python -m pytest -q uk_management_bot/tests/handlers` → зелёные (кроме известных локальных красных в utils); `make test-ci` → зелёный.
- [ ] `docs/bugs-2026-09-03.md` — раздел BUG-188 (диагноз + фикс); `docs/audit/2026-05-20-backlog.md` — при наличии пункта про документы.
- [ ] Ветка `fix/bug188-document-upload-entry`, PR, CI, мерж.
- [ ] Раскатка `app` на profk и 105 (skill uk-deploy: build api access-api app migrate → migrate → up api/access-api/app; фронт не трогаем), теги.
- [ ] Проверка владельцем: менеджер «Запросить документы» → у жителя сообщение с кнопкой → тип → фото → «документ сохранён»; фото «из ниоткуда» → подсказка с кнопкой.
