# 📋 Техническое задание на миграцию UK Management Bot в микросервисную архитектуру

**Дата создания**: 7 октября 2025  
**Версия**: 1.0  
**Источник**: Анализ монолитного бота `uk_management_bot/`  
**Цель**: Полная миграция функциональности в Bot Gateway Service

---

## 📊 EXECUTIVE SUMMARY

### Масштаб проекта

| Метрика | Монолитный бот | Требуется в Bot Gateway |
|---------|----------------|------------------------|
| **Handlers (файлов)** | 24 | 24 |
| **Обработчиков** | 419 (@router.message/@callback_query) | 419 |
| **Keyboards (файлов)** | 18 | 18 |
| **Кнопок** | 916 (Inline + Reply) | 916 |
| **FSM States (файлов)** | 16 | 16 |
| **Строк кода** | ~24,346 | ~25,000-30,000 |
| **FSM StatesGroup** | 28 | 28 |

### Структура монолитного бота

```
uk_management_bot/
├── main.py (252 строки) - точка входа
├── handlers/ (24 файла)
│   ├── base.py, auth.py, requests.py, shifts.py
│   ├── admin.py, user_management.py, employee_management.py
│   ├── request_assignment.py, request_status_management.py
│   ├── request_comments.py, request_reports.py
│   ├── shift_management.py, shift_transfer.py, my_shifts.py
│   ├── building_selection.py, request_with_building.py
│   ├── user_verification.py, onboarding.py
│   ├── profile_editing.py, quarterly_planning.py
│   └── clarification_replies.py, health.py
├── keyboards/ (18 файлов)
│   ├── base.py (162 строки) - главные клавиатуры
│   ├── requests.py (452 строки) - заявки
│   ├── admin.py (148 строк) - админ панель
│   ├── shifts.py (67 строк) - смены
│   └── ... (14 других файлов)
├── states/ (16 файлов)
│   ├── registration.py, onboarding.py, user_verification.py
│   ├── request_status.py, request_comments.py, request_assignment.py
│   ├── shift_management.py (192 строки), shift_transfer.py
│   └── ... (8 других файлов)
├── services/ - бизнес-логика
├── middlewares/ - auth, shift context
├── database/ - SQLAlchemy модели
└── utils/ - helpers, constants
```

---

## 🎯 ДЕТАЛЬНАЯ СПЕЦИФИКАЦИЯ ПО МОДУЛЯМ

### 1️⃣ БАЗОВЫЙ ФУНКЦИОНАЛ (base.py, auth.py)

#### Обработчики (13)

**base.py**:
```python
@router.message(Command("start"))         # /start - приветствие
@router.message(Command("help"))          # /help - справка
@router.message(F.text == "ℹ️ Помощь")    # Кнопка помощи
@router.message(F.text == "👤 Профиль")   # Просмотр профиля
@router.message(F.text == "🔙 Назад")     # Возврат в главное меню
@router.callback_query(F.data.startswith("switch_role:"))  # Переключение роли
@router.callback_query(F.data == "suggest_executor_skip")  # Пропуск предложения роли
```

**auth.py**:
```python
@router.message(F.text == "🔀 Выбрать роль")  # Переключение между ролями
@router.callback_query(F.data.startswith("switch_role:"))  # Callback переключения
```

#### Клавиатуры (base.py - 162 строки)

**Главные клавиатуры**:
1. `get_main_keyboard()` - базовая клавиатура
2. `get_main_keyboard_for_role(active_role, roles)` - контекстная по роли
   - **applicant**: 📝 Создать заявку, 📋 Мои заявки, 👤 Профиль, ℹ️ Помощь
   - **executor**: 🛠 Активные заявки, 📦 Архив, 👤 Профиль, ℹ️ Помощь, 🔄 Смена, 📋 Мои смены
   - **manager/admin**: + 🔧 Админ панель
3. `get_user_contextual_keyboard(user_id)` - динамическая загрузка из БД
4. `get_role_switch_inline(roles, active_role)` - переключение ролей inline
5. `get_executor_suggestion_inline()` - предложение роли исполнителя
6. `get_cancel_keyboard()` - ❌ Отмена
7. `get_yes_no_keyboard()` - ✅ Да / ❌ Нет / 🔙 Назад
8. `get_rating_keyboard()` - ⭐⭐⭐⭐⭐ (1-5 звезд)

**FSM States**: нет (базовый функционал)

---

### 2️⃣ РЕГИСТРАЦИЯ И ONBOARDING (auth.py, onboarding.py, registration.py)

#### FSM States (registration.py + onboarding.py)

**RegistrationStates** (17 строк):
```python
class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_position_confirmation = State()
    waiting_for_additional_info = State()
```

**OnboardingStates** (25 строк):
```python
class OnboardingStates(StatesGroup):
    welcome = State()
    tutorial_step_1 = State()  # Как создать заявку
    tutorial_step_2 = State()  # Отслеживание статуса
    tutorial_step_3 = State()  # Работа со сменами
    tutorial_step_4 = State()  # Профиль и настройки
    tutorial_step_5 = State()  # Помощь и поддержка
    onboarding_complete = State()
```

#### Обработчики (13)

**onboarding.py**:
```python
@router.message(F.text == "🚀 Начать обучение")
@router.callback_query(F.data == "onboarding_start")
@router.callback_query(F.data.startswith("onboarding_"))  # Навигация по шагам
@router.message(OnboardingStates.tutorial_step_1)
# ... для каждого шага
```

#### Клавиатуры (onboarding.py - 24 кнопки)

1. `get_onboarding_start_keyboard()` - 🚀 Начать обучение / ⏭️ Пропустить
2. `get_onboarding_step_keyboard(step)` - ⏭️ Далее / ⏮️ Назад / ❌ Пропустить
3. `get_onboarding_complete_keyboard()` - ✅ Завершить обучение

---

### 3️⃣ ВЕРИФИКАЦИЯ ПОЛЬЗОВАТЕЛЕЙ (user_verification.py)

#### FSM States (user_verification.py - 29 строк)

```python
class UserVerificationStates(StatesGroup):
    waiting_for_passport_photo = State()
    waiting_for_verification_selfie = State()
    waiting_for_documents = State()
    verification_review = State()
```

#### Обработчики (13)

```python
@router.message(F.text == "📸 Загрузить документы")
@router.message(F.photo, UserVerificationStates.waiting_for_passport_photo)
@router.message(F.photo, UserVerificationStates.waiting_for_verification_selfie)
@router.callback_query(F.data.startswith("verify_user_"))  # Админ: верификация
@router.callback_query(F.data.startswith("reject_verification_"))
```

#### Клавиатуры (user_verification.py - 576 строк, 83 кнопки)

1. `get_verification_start_keyboard()` - 📸 Начать верификацию
2. `get_document_upload_keyboard()` - 📤 Загрузить / ⏭️ Пропустить / ❌ Отмена
3. `get_verification_admin_keyboard(user_id)` - ✅ Одобрить / ❌ Отклонить / 👁️ Просмотр
4. `get_document_actions_keyboard(doc_id)` - ✅ Подтвердить / ❌ Отклонить / 📝 Комментарий

---

### 4️⃣ УПРАВЛЕНИЕ ПРОФИЛЕМ (profile_editing.py)

#### FSM States (profile_editing.py - 23 строки)

```python
class ProfileEditingStates(StatesGroup):
    editing_full_name = State()
    editing_phone = State()
    editing_specialization = State()
    editing_photo = State()
```

#### Обработчики (18)

```python
@router.message(F.text == "✏️ Редактировать профиль")
@router.message(F.text == "📝 Изменить имя")
@router.message(F.text == "📞 Изменить телефон")
@router.message(F.text == "🛠️ Изменить специализацию")
@router.message(F.text == "📸 Изменить фото")
@router.message(ProfileEditingStates.editing_full_name)
@router.message(ProfileEditingStates.editing_phone)
# ... для каждого поля
```

#### Клавиатуры (profile.py - 166 строк, 24 кнопки)

1. `get_profile_menu_keyboard()` - ✏️ Редактировать / 📊 Статистика / 🔙 Назад
2. `get_profile_edit_keyboard()` - 📝 Имя / 📞 Телефон / 🛠️ Специализация / 📸 Фото / 🔙 Назад
3. `get_specialization_keyboard()` - 🔧 Сантехник / ⚡ Электрик / ... (9 специализаций)

---

### 5️⃣ ЗАЯВКИ (requests.py, request_*.py) - ОСНОВНОЙ МОДУЛЬ

#### FSM States (4 файла)

**request_status.py** (20 строк):
```python
class RequestStatusStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_address = State()
    waiting_for_description = State()
    waiting_for_urgency = State()
    waiting_for_apartment = State()
    waiting_for_media = State()
    confirmation = State()
```

**request_comments.py** (14 строк):
```python
class RequestCommentStates(StatesGroup):
    waiting_for_comment = State()
```

**request_assignment.py** (21 строка):
```python
class RequestAssignmentStates(StatesGroup):
    waiting_for_executor_selection = State()
    waiting_for_assignment_comment = State()
```

**request_reports.py** (15 строк):
```python
class RequestReportStates(StatesGroup):
    waiting_for_report_period = State()
    waiting_for_report_format = State()
```

#### Обработчики (37+ в requests.py + ~40 в других)

**requests.py** (основной):
```python
@router.message(F.text == "📝 Создать заявку")
@router.message(F.text == "📋 Мои заявки")
@router.callback_query(F.data.startswith("category_"))  # Выбор категории
@router.callback_query(F.data.startswith("urgency_"))   # Выбор срочности
@router.callback_query(F.data == "confirm_yes")         # Подтверждение
@router.callback_query(F.data == "confirm_no")          # Отмена
@router.callback_query(F.data.startswith("view_"))      # Просмотр заявки
@router.callback_query(F.data.startswith("edit_"))      # Редактирование
@router.callback_query(F.data.startswith("delete_"))    # Удаление
@router.callback_query(F.data.startswith("page_"))      # Пагинация
@router.callback_query(F.data.startswith("status_"))    # Фильтр по статусу
@router.callback_query(F.data.startswith("categoryfilter_"))  # Фильтр по категории
```

**request_status_management.py** (10 обработчиков):
```python
@router.callback_query(F.data.startswith("accept_"))     # 🔧 В работу
@router.callback_query(F.data.startswith("work_"))       # 🔄 В работе
@router.callback_query(F.data.startswith("purchase_"))   # 💰 Закуп
@router.callback_query(F.data.startswith("clarify_"))    # ❓ Уточнение
@router.callback_query(F.data.startswith("complete_"))   # ✅ Выполнена
@router.callback_query(F.data.startswith("approve_"))    # ✅ Подтвердить
@router.callback_query(F.data.startswith("cancel_"))     # ❌ Отменить
@router.callback_query(F.data.startswith("deny_"))       # 🚫 Предложить отказ
```

**request_comments.py** (8 обработчиков):
```python
@router.callback_query(F.data.startswith("comment_"))    # Добавить комментарий
@router.message(RequestCommentStates.waiting_for_comment)
@router.callback_query(F.data.startswith("delete_comment_"))  # Удалить комментарий
```

**request_assignment.py** (8 обработчиков):
```python
@router.callback_query(F.data.startswith("assign_"))     # Назначить исполнителя
@router.callback_query(F.data.startswith("executor_"))   # Выбор исполнителя
@router.callback_query(F.data.startswith("reassign_"))   # Переназначить
```

**clarification_replies.py** (2 обработчика):
```python
@router.callback_query(F.data.startswith("replyclarify_"))  # Ответить на уточнение
@router.message(F.text, states=[...])  # Обработка ответа
```

#### Клавиатуры (requests.py - 452 строки, 77+ кнопок)

**Основные клавиатуры**:
1. `get_categories_keyboard()` - Категории заявок (Reply)
   - 🔧 Сантехника
   - ⚡ Электрика
   - 🌡️ Отопление
   - 🚪 Двери/замки
   - 🪟 Окна
   - 🔨 Ремонт
   - 🧹 Уборка
   - 🌳 Благоустройство
   - ❌ Отмена

2. `get_categories_inline_keyboard()` - То же inline (CALLBACK_PREFIX_CATEGORY)

3. `get_urgency_keyboard()` - Срочность (Reply)
   - 🔴 Срочно
   - 🟡 Средняя
   - 🟢 Несрочно
   - ❌ Отмена

4. `get_urgency_inline_keyboard()` - То же inline (CALLBACK_PREFIX_URGENCY)

5. `get_media_keyboard()` - Загрузка медиа
   - ▶️ Продолжить
   - ❌ Отмена

6. `get_confirmation_keyboard()` - Подтверждение
   - ✅ Подтвердить
   - 🔙 Назад
   - ❌ Отмена

7. `get_inline_confirmation_keyboard()` - То же inline
   - ✅ Подтвердить (callback: confirm_yes)
   - ❌ Отмена (callback: confirm_no)

8. `get_request_actions_keyboard(request_number)` - Действия с заявкой
   - 👁️ Просмотр
   - ✏️ Редактировать
   - 🔧 В работу
   - ❓ Уточнение
   - 🔄 В работе
   - 💰 Закуп
   - ✅ Выполнена
   - ✅ Подтвердить
   - ❌ Отменить
   - 🚫 Предложить отказ

9. `get_pagination_keyboard(current_page, total_pages, request_number)` - Пагинация
   - ◀️ Назад
   - {current_page}/{total_pages}
   - ▶️ Вперед
   - + кнопки действий с заявкой

**Фильтры**:
10. `get_status_filter_inline_keyboard(active_status)` - Фильтр по статусу
    - Активные (status_active)
    - Архив (status_archive)

11. `get_category_filter_inline_keyboard(active_category)` - Фильтр по категории
    - Все категории (categoryfilter_all)
    - + каждая категория (categoryfilter_{category})

12. `get_period_filter_inline_keyboard(active_period)` - Фильтр по периоду
    - Все время (period_all)
    - 7 дней (period_7d)
    - 30 дней (period_30d)
    - 90 дней (period_90d)

13. `get_executor_filter_inline_keyboard(active_executor)` - Фильтр исполнителя
    - Все исполнители (executorfilter_all)
    - Я исполнитель (executorfilter_me)

14. `get_reset_filters_inline_keyboard()` - Сброс фильтров

**Адреса**:
15. `get_address_selection_keyboard(user_id)` - Динамический выбор адреса
    - {ADDRESS_TYPE_DISPLAY}: {address} (из БД пользователя)
    - ✏️ Ввести адрес вручную
    - ❌ Отмена

16. `parse_selected_address(selected_text)` - Парсер выбранного адреса

---

### 6️⃣ СМЕНЫ (shifts.py, my_shifts.py, shift_*.py)

#### FSM States (3 файла, 235 строк)

**my_shifts.py** (235 строк - самый большой):
```python
class MyShiftsStates(StatesGroup):
    viewing_shifts = State()
    shift_details = State()
```

**shift_transfer.py** (28 строк):
```python
class ShiftTransferStates(StatesGroup):
    waiting_for_transfer_recipient = State()
    waiting_for_transfer_reason = State()
    transfer_confirmation = State()
```

**shift_management.py** (192 строки):
```python
class ShiftManagementStates(StatesGroup):
    # Создание смены
    waiting_for_shift_executor = State()
    waiting_for_shift_date = State()
    waiting_for_shift_time_start = State()
    waiting_for_shift_time_end = State()
    waiting_for_shift_description = State()
    
    # Редактирование
    editing_shift = State()
    waiting_for_new_executor = State()
    waiting_for_new_date = State()
    
    # Удаление
    confirming_shift_deletion = State()
    
    # Просмотр
    viewing_shift_list = State()
    viewing_shift_details = State()
```

#### Обработчики (13+ в shifts.py + ~60 в других)

**shifts.py** (основной):
```python
@router.message(F.text == "🔄 Смена")
@router.message(F.text == "📋 Мои смены")
@router.message(F.text == "🔄 Принять смену")
@router.message(F.text == "🔚 Сдать смену")
@router.message(F.text == "ℹ️ Моя смена")
@router.message(F.text == "📜 История смен")
@router.callback_query(F.data == "shift_end_confirm_yes")
@router.callback_query(F.data == "shift_end_confirm_no")
```

**my_shifts.py** (12 обработчиков):
```python
@router.message(F.text == "📋 Мои смены")
@router.callback_query(F.data.startswith("shifts_period_"))  # Фильтр период
@router.callback_query(F.data.startswith("shifts_status_"))  # Фильтр статус
@router.callback_query(F.data == "shifts_filters_reset")      # Сброс фильтров
@router.callback_query(F.data.startswith("shifts_page_"))     # Пагинация
```

**shift_transfer.py** (13 обработчиков):
```python
@router.message(F.text == "🔄 Передать смену")
@router.message(F.text, ShiftTransferStates.waiting_for_transfer_recipient)
@router.message(F.text, ShiftTransferStates.waiting_for_transfer_reason)
@router.callback_query(F.data == "transfer_confirm")
@router.callback_query(F.data == "transfer_cancel")
```

**shift_management.py** (58 обработчиков - admin):
```python
@router.message(F.text == "📅 Управление сменами")
@router.message(F.text == "➕ Создать смену")
@router.message(F.text == "📋 Список смен")
@router.callback_query(F.data.startswith("shift_view_"))      # Просмотр
@router.callback_query(F.data.startswith("shift_edit_"))      # Редактирование
@router.callback_query(F.data.startswith("shift_delete_"))    # Удаление
@router.callback_query(F.data.startswith("force_end_shift_")) # Принудительное завершение
# ... много обработчиков для создания/редактирования
```

#### Клавиатуры (shifts.py - 67 строк + my_shifts.py - 102 кнопки)

**shifts.py**:
1. `get_shifts_main_keyboard()` - Главное меню смен
   - 🔄 Принять смену
   - 🔚 Сдать смену
   - ℹ️ Моя смена
   - 📜 История смен
   - 🔙 Назад

2. `get_end_shift_confirm_inline()` - Подтверждение завершения
   - ✅ Да (shift_end_confirm_yes)
   - ❌ Нет (shift_end_confirm_no)

**my_shifts.py**:
3. `get_shifts_filters_inline(period, status)` - Фильтры
   - Период: Все время / Сегодня / 7д / 30д / 90д (shifts_period_*)
   - Статус: Все / Активные / Завершенные / Отмененные (shifts_status_*)
   - Сброс фильтров (shifts_filters_reset)

4. `get_pagination_inline(current_page, total_pages)` - Пагинация
   - ◀️ / {page}/{total} / ▶️ (shifts_page_*)

5. `get_manager_active_shifts_row(telegram_id)` - Админ: принудительное завершение
   - ❗ Завершить смену (force_end_shift_{telegram_id})

**shift_transfer.py** (422 строки, 36 кнопок):
6. `get_transfer_confirmation_keyboard()` - Подтверждение передачи
7. `get_available_executors_keyboard(executors)` - Список доступных исполнителей
8. `get_shift_transfer_history_keyboard()` - История передач

**shift_management.py** (264 строки, 89 кнопок):
9. `get_shift_management_keyboard()` - Управление сменами (admin)
   - ➕ Создать смену
   - 📋 Список смен
   - 📊 Статистика
   - 🔙 Назад

10. `get_shift_actions_keyboard(shift_id)` - Действия со сменой
    - 👁️ Просмотр
    - ✏️ Редактировать
    - 🗑️ Удалить
    - ❗ Завершить принудительно

11. `get_shift_edit_keyboard()` - Редактирование смены
    - 👤 Исполнитель
    - 📅 Дата
    - ⏰ Время
    - 📝 Описание

---

### 7️⃣ АДМИН ПАНЕЛЬ (admin.py, user_management.py, employee_management.py)

#### FSM States (3 файла)

**user_management.py** (58 строк):
```python
class UserManagementStates(StatesGroup):
    viewing_user_list = State()
    viewing_user_details = State()
    editing_user_role = State()
    deactivating_user = State()
```

**employee_management.py** (61 строка):
```python
class EmployeeManagementStates(StatesGroup):
    selecting_employee = State()
    viewing_employee_details = State()
    editing_employee_specialization = State()
    editing_employee_status = State()
```

**invite_creation.py** (19 строк):
```python
class InviteCreationStates(StatesGroup):
    waiting_for_invite_role = State()
    waiting_for_invite_count = State()
    waiting_for_invite_specialization = State()
    waiting_for_invite_expiry = State()
    invite_confirmation = State()
```

#### Обработчики (30 в admin.py + 43 в user_management + 28 в employee_management)

**admin.py** (30 обработчиков):
```python
@router.message(F.text == "🔧 Админ панель")
@router.message(F.text == "🆕 Новые заявки")
@router.message(F.text == "🔄 Активные заявки")
@router.message(F.text == "💰 Закуп")
@router.message(F.text == "📦 Архив")
@router.message(F.text == "👥 Смены")
@router.message(F.text == "👥 Управление пользователями")
@router.message(F.text == "👷 Управление сотрудниками")
@router.message(F.text == "📨 Создать приглашение")
@router.callback_query(F.data.startswith("mview_"))     # Просмотр заявки
@router.callback_query(F.data.startswith("mreq_page_")) # Пагинация
```

**user_management.py** (43 обработчика):
```python
@router.message(F.text == "👥 Управление пользователями")
@router.callback_query(F.data.startswith("user_page_"))   # Пагинация
@router.callback_query(F.data.startswith("view_user_"))   # Просмотр
@router.callback_query(F.data.startswith("edit_user_"))   # Редактирование
@router.callback_query(F.data.startswith("approve_user_")) # Одобрить
@router.callback_query(F.data.startswith("reject_user_"))  # Отклонить
@router.callback_query(F.data.startswith("block_user_"))   # Заблокировать
@router.callback_query(F.data.startswith("unblock_user_")) # Разблокировать
```

**employee_management.py** (28 обработчиков):
```python
@router.message(F.text == "👷 Управление сотрудниками")
@router.callback_query(F.data.startswith("employee_"))       # Выбор сотрудника
@router.callback_query(F.data.startswith("edit_employee_"))  # Редактирование
@router.callback_query(F.data.startswith("change_spec_"))    # Изменить специализацию
@router.callback_query(F.data.startswith("change_status_"))  # Изменить статус
```

#### Клавиатуры (admin.py - 148 строк, 46 кнопок)

**admin.py**:
1. `get_manager_main_keyboard()` - Главное меню админа
   - 🆕 Новые заявки
   - 🔄 Активные заявки
   - 💰 Закуп
   - 📦 Архив
   - 👥 Смены
   - 👥 Управление пользователями
   - 👷 Управление сотрудниками
   - 📨 Создать приглашение
   - 🔙 Назад

2. `get_manager_requests_inline(page, total_pages)` - Пагинация для менеджера

3. `get_manager_request_list_kb(requests, page, total_pages)` - Список заявок
   - {icon} #{request_number} • {category} • {address} (mview_{request_number})
   - Пагинация (mreq_page_*)

4. `get_manager_request_actions_keyboard(request_number)` - Действия менеджера
   - 🔧 В работу
   - ❌ Отклонить
   - ❓ Уточнить
   - 💰 В закуп
   - ✅ Завершить
   - 🗑️ Удалить

**Приглашения**:
5. `get_invite_role_keyboard()` - Выбор роли
   - 👤 Заявитель (invite_role_applicant)
   - 🛠️ Исполнитель (invite_role_executor)
   - 👨‍💼 Менеджер (invite_role_manager)
   - ❌ Отмена (invite_cancel)

6. `get_invite_specialization_keyboard()` - Специализация (9 кнопок)
   - 🔧 Сантехник
   - ⚡ Электрик
   - 🌡️ Отопление/вентиляция
   - 🧹 Уборка
   - 🔒 Охрана
   - 🔧 Обслуживание
   - 🌳 Благоустройство
   - 🔨 Ремонт
   - 📦 Установка

7. `get_invite_expiry_keyboard()` - Срок действия
   - ⏰ 1 час
   - 📅 24 часа
   - 📆 7 дней

8. `get_invite_confirmation_keyboard()` - Подтверждение
   - ✅ Создать приглашение
   - ❌ Отмена

**user_management.py** (510 строк, 72 кнопки):
9. `get_user_management_keyboard()` - Управление пользователями
   - 👥 Список пользователей
   - 🆕 На модерации
   - 🔍 Поиск
   - 🔙 Назад

10. `get_user_approval_keyboard(user_id)` - Одобрение
    - ✅ Одобрить (approve_user_{id})
    - ❌ Отклонить (reject_user_{id})
    - 👁️ Просмотреть профиль (view_user_{id})

11. `get_user_actions_keyboard(user_id)` - Действия с пользователем
    - ✏️ Редактировать
    - 🔒 Заблокировать
    - 🗑️ Удалить
    - 🔙 Назад

12. `get_user_edit_keyboard()` - Редактирование пользователя
    - 👤 Роль
    - 🛠️ Специализация
    - 📞 Телефон
    - 🔙 Назад

**employee_management.py** (576 строк, 61 кнопка):
13. `get_employee_management_keyboard()` - Управление сотрудниками
    - 📋 Список сотрудников
    - 🔍 Поиск
    - 📊 Статистика
    - 🔙 Назад

14. `get_employee_list_keyboard(employees, page)` - Список сотрудников
15. `get_employee_actions_keyboard(employee_id)` - Действия с сотрудником
16. `get_specialization_change_keyboard()` - Изменение специализации
17. `get_employee_status_keyboard()` - Изменение статуса

---

### 8️⃣ СПРАВОЧНИК ЗДАНИЙ (building_selection.py, request_with_building.py)

#### FSM States (building_selection.py - 72 строки)

```python
class BuildingSelectionStates(StatesGroup):
    selecting_building = State()
    entering_building_address = State()
    confirming_building = State()
```

**Дополнительные states для заявок**:
```python
class RequestWithBuildingStates(StatesGroup):
    waiting_for_building = State()
    waiting_for_apartment = State()
    waiting_for_entrance = State()
```

#### Обработчики (10 в building_selection + 6 в request_with_building)

**building_selection.py**:
```python
@router.message(F.text == "🏢 Выбрать здание")
@router.callback_query(F.data.startswith("building_"))      # Выбор из списка
@router.callback_query(F.data == "building_manual")         # Ручной ввод
@router.message(BuildingSelectionStates.entering_building_address)
```

**request_with_building.py**:
```python
@router.message(F.text, RequestWithBuildingStates.waiting_for_building)
@router.message(F.text, RequestWithBuildingStates.waiting_for_apartment)
@router.callback_query(F.data.startswith("confirm_building_"))
```

#### Клавиатуры (buildings.py - 25 кнопок)

1. `get_building_selection_keyboard(buildings)` - Список зданий
   - {building.address} (building_{id})
   - ✏️ Ввести вручную (building_manual)
   - ❌ Отмена

2. `get_building_confirmation_keyboard(building_id)` - Подтверждение
   - ✅ Подтвердить (confirm_building_{id})
   - 🔙 Назад
   - ❌ Отмена

3. `get_building_management_keyboard()` - Управление справочником (admin)
   - ➕ Добавить здание
   - 📋 Список зданий
   - 🔍 Поиск
   - 🔙 Назад

---

### 9️⃣ КВАРТАЛЬНОЕ ПЛАНИРОВАНИЕ (quarterly_planning.py)

#### FSM States (quarterly_planning.py - 44 строки)

```python
class QuarterlyPlanningStates(StatesGroup):
    selecting_quarter = State()
    selecting_building = State()
    selecting_category = State()
    entering_description = State()
    entering_budget = State()
    confirming_plan = State()
```

#### Обработчики (11)

```python
@router.message(F.text == "📊 Квартальное планирование")
@router.callback_query(F.data.startswith("quarter_"))       # Выбор квартала
@router.callback_query(F.data.startswith("plan_building_")) # Выбор здания
@router.callback_query(F.data.startswith("plan_category_")) # Выбор категории
@router.message(QuarterlyPlanningStates.entering_description)
@router.message(QuarterlyPlanningStates.entering_budget)
@router.callback_query(F.data == "confirm_plan")
```

#### Клавиатуры (quarterly_planning.py - 322 строки, 92 кнопки)

1. `get_quarterly_planning_keyboard()` - Главное меню
   - 📅 Текущий квартал
   - 📊 Следующий квартал
   - 📜 История
   - 🔙 Назад

2. `get_quarter_selection_keyboard()` - Выбор квартала
   - Q1 2025 / Q2 2025 / Q3 2025 / Q4 2025

3. `get_plan_category_keyboard()` - Категории планирования
   - 🔧 Текущий ремонт
   - 🏗️ Капитальный ремонт
   - 🌳 Благоустройство
   - 🔒 Безопасность
   - 💡 Энергоэффективность

4. `get_plan_actions_keyboard(plan_id)` - Действия с планом
   - 👁️ Просмотр
   - ✏️ Редактировать
   - ✅ Утвердить
   - ❌ Отклонить

---

### 🔟 ОТЧЕТЫ (request_reports.py)

#### FSM States (request_reports.py - 15 строк)

```python
class RequestReportStates(StatesGroup):
    waiting_for_report_period = State()
    waiting_for_report_format = State()
```

#### Обработчики (7)

```python
@router.message(F.text == "📊 Отчеты")
@router.callback_query(F.data.startswith("report_period_"))  # Выбор периода
@router.callback_query(F.data.startswith("report_format_"))  # Выбор формата
@router.callback_query(F.data == "report_generate")          # Генерация
```

#### Клавиатуры (request_reports.py - 138 строк, 22 кнопки)

1. `get_reports_menu_keyboard()` - Меню отчетов
   - 📊 Отчет по заявкам
   - 📈 Отчет по сменам
   - 💰 Финансовый отчет
   - 🔙 Назад

2. `get_report_period_keyboard()` - Выбор периода
   - 📅 За неделю
   - 📆 За месяц
   - 📊 За квартал
   - 📈 За год
   - 📋 Произвольный период

3. `get_report_format_keyboard()` - Выбор формата
   - 📄 PDF
   - 📊 Excel
   - 📧 Email
   - 💬 Telegram

---

## 📊 SUMMARY ТАБЛИЦА ВСЕХ FSM STATES

| № | StatesGroup | Файл | Количество states | Приоритет |
|---|-------------|------|-------------------|-----------|
| 1 | RegistrationStates | registration.py | 4 | 🔴 P0 |
| 2 | OnboardingStates | onboarding.py | 7 | 🔴 P0 |
| 3 | UserVerificationStates | user_verification.py | 4 | 🔴 P0 |
| 4 | ProfileEditingStates | profile_editing.py | 4 | 🟡 P1 |
| 5 | InviteCreationStates | invite_creation.py | 5 | 🟡 P1 |
| 6 | RequestStatusStates | request_status.py | 7 | ✅ Есть (частично) |
| 7 | RequestCommentStates | request_comments.py | 1 | ✅ Есть |
| 8 | RequestAssignmentStates | request_assignment.py | 2 | ✅ Есть (частично) |
| 9 | RequestReportStates | request_reports.py | 2 | 🟢 P3 |
| 10 | BuildingSelectionStates | building_selection.py | 3 | 🟡 P1 |
| 11 | RequestWithBuildingStates | (custom) | 3 | 🟡 P1 |
| 12 | MyShiftsStates | my_shifts.py | 2 | ✅ Есть (частично) |
| 13 | ShiftTransferStates | shift_transfer.py | 3 | ✅ Есть |
| 14 | ShiftManagementStates | shift_management.py | 13 | 🟠 P2 |
| 15 | ShiftTimeTrackingStates | (custom) | 3 | 🟠 P2 |
| 16 | ShiftEmergencyStates | (custom) | 3 | 🟠 P2 |
| 17 | ShiftReportingStates | (custom) | 2 | 🟠 P2 |
| 18 | UserManagementStates | user_management.py | 4 | ✅ Есть |
| 19 | EmployeeManagementStates | employee_management.py | 4 | 🟡 P1 |
| 20 | QuarterlyPlanningStates | quarterly_planning.py | 6 | 🟢 P3 |
| **ИТОГО** | **20 StatesGroup** | **16 файлов** | **82 states** | **15 missing** |

---

## 📈 ПРИОРИТИЗАЦИЯ МИГРАЦИИ

### **Phase 1: Critical Blockers (P0)** - 3-4 дня

**ОБЯЗАТЕЛЬНЫ для production**:

1. **RegistrationStates** (4 states) - Регистрация новых пользователей
   - Handlers: 7+
   - Keyboards: 3
   - Effort: 1 день

2. **UserVerificationStates** (4 states) - KYC верификация
   - Handlers: 13
   - Keyboards: 4 (576 строк!)
   - Effort: 1.5 дня

3. **OnboardingStates** (7 states) - Onboarding новых юзеров
   - Handlers: 13
   - Keyboards: 3
   - Effort: 1 день

**Total P0**: 3-3.5 дня (1 dev)

---

### **Phase 2: High Priority (P1)** - 5-6 дней

**Важные функции**:

4. **ProfileEditingStates** (4 states) - Редактирование профиля
   - Handlers: 18
   - Keyboards: 3
   - Effort: 1 день

5. **InviteCreationStates** (5 states) - Создание приглашений
   - Handlers: 10
   - Keyboards: 4
   - Effort: 1 день

6. **EmployeeManagementStates** (4 states) - Управление сотрудниками
   - Handlers: 28
   - Keyboards: 5
   - Effort: 1.5 дня

7. **BuildingSelectionStates** (3 states) - Выбор здания
   - Handlers: 10
   - Keyboards: 3
   - Effort: 1 день

8. **RequestWithBuildingStates** (3 states) - Заявки с зданиями
   - Handlers: 6
   - Keyboards: 2
   - Effort: 0.5 дня

**Total P1**: 5-6 дней (1 dev)

---

### **Phase 3: Medium Priority (P2)** - 4-5 дней

**Advanced features**:

9. **ShiftManagementStates** (13 states) - Управление сменами (admin)
   - Handlers: 58
   - Keyboards: 11
   - Effort: 2.5 дня

10. **ShiftTimeTrackingStates** (3 states) - Учет времени смен
    - Handlers: 8
    - Keyboards: 3
    - Effort: 0.5 дня

11. **ShiftEmergencyStates** (3 states) - Экстренные ситуации
    - Handlers: 6
    - Keyboards: 2
    - Effort: 0.5 дня

12. **ShiftReportingStates** (2 states) - Отчеты по сменам
    - Handlers: 7
    - Keyboards: 3
    - Effort: 0.5 дня

**Total P2**: 4-5 дней (1 dev)

---

### **Phase 4: Low Priority (P3)** - 1-2 дня

**Nice to have**:

13. **RequestReportStates** (2 states) - Отчеты по заявкам
    - Handlers: 7
    - Keyboards: 3
    - Effort: 0.5 дня

14. **QuarterlyPlanningStates** (6 states) - Квартальное планирование
    - Handlers: 11
    - Keyboards: 4
    - Effort: 1 день

**Total P3**: 1.5 дня (1 dev)

---

## ⏱️ ИТОГОВАЯ ОЦЕНКА EFFORT

| Фаза | Задачи | Handlers | Keyboards | States | Effort (1 dev) | Effort (2 devs) |
|------|--------|----------|-----------|--------|----------------|-----------------|
| **P0** | 3 | 33 | 10 | 15 | 3-4 дня | 2 дня |
| **P1** | 5 | 72 | 17 | 19 | 5-6 дней | 3 дня |
| **P2** | 4 | 79 | 19 | 21 | 4-5 дней | 2.5 дня |
| **P3** | 2 | 18 | 7 | 8 | 1.5 дня | 1 день |
| **ИТОГО** | **14** | **202** | **53** | **63** | **14-16.5 дней** | **8.5 дней** |

**Текущий статус Bot Gateway**: 15/28 StatesGroup (54%)  
**Требуется добавить**: 13 StatesGroup (46%)  
**Effort с командой (2-3 devs)**: **8-9 дней**

---

## 🔄 ИНТЕГРАЦИЯ С МИКРОСЕРВИСАМИ

### Service Clients Required

Каждый handler должен вызывать соответствующие микросервисы:

```python
# Примеры интеграций

# 1. Регистрация -> User Service
user_client = UserServiceClient()
user_data = await user_client.create_user(telegram_id, full_name, phone)

# 2. Заявки -> Request Service
request_client = RequestServiceClient()
request = await request_client.create_request(category, address, description)

# 3. Смены -> Shift Service
shift_client = ShiftServiceClient()
shift = await shift_client.start_shift(executor_id)

# 4. Здания -> Integration Service -> Building Directory
integration_client = IntegrationServiceClient()
building = await integration_client.get_building(address)

# 5. Геокодинг -> Integration Service
coords = await integration_client.forward_geocode(address)

# 6. Уведомления -> Notification Service
notification_client = NotificationServiceClient()
await notification_client.send_notification(user_id, template_id, data)
```

### Event Publishing Required

```python
# Events для Analytics Service

# 1. Request events
await publish_event("request.created", {request_id, category, urgency})
await publish_event("request.status_changed", {request_id, old_status, new_status})

# 2. Shift events
await publish_event("shift.started", {shift_id, executor_id, timestamp})
await publish_event("shift.ended", {shift_id, duration, timestamp})

# 3. User events
await publish_event("user.registered", {user_id, telegram_id, timestamp})
await publish_event("user.verified", {user_id, timestamp})
```

---

## 📝 ЧЕКЛИСТ МИГРАЦИИ

### Для каждого handler файла

- [ ] Создать файл в `bot_gateway/app/routers/`
- [ ] Скопировать FSM states в `bot_gateway/app/states/`
- [ ] Создать клавиатуры в `bot_gateway/app/keyboards/`
- [ ] Заменить прямые вызовы БД на service clients
- [ ] Добавить event publishing
- [ ] Написать unit tests
- [ ] Написать integration tests
- [ ] Обновить документацию

### Для каждой клавиатуры

- [ ] Скопировать функцию генерации
- [ ] Проверить callback_data совпадают
- [ ] Проверить emoji совпадают
- [ ] Проверить тексты кнопок совпадают
- [ ] Проверить layout (2/3 кнопки в ряд)

### Для каждого FSM state

- [ ] Скопировать StatesGroup
- [ ] Скопировать handlers для каждого state
- [ ] Проверить transitions между states
- [ ] Добавить error handling
- [ ] Добавить cancel handlers

---

## 🎯 КЛЮЧЕВЫЕ ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ

### 1. Совместимость callback_data

**Критично**: Все callback_data должны совпадать с монолитом

```python
# Монолит
callback_data=f"accept_{request_number}"

# Bot Gateway (ДОЛЖНО СОВПАДАТЬ)
callback_data=f"accept_{request_number}"
```

### 2. Структура сообщений

Все шаблоны сообщений должны совпадать:
- Emoji
- Форматирование (bold, italic, code)
- Структура текста
- Numbered lists

### 3. Middleware

Требуется перенести:
- `auth_middleware` - аутентификация через Auth Service
- `role_mode_middleware` - контекст активной роли
- `shift_context_middleware` - контекст активной смены

### 4. Utils/Helpers

Требуется перенести:
- `REQUEST_CATEGORIES`, `REQUEST_URGENCIES`, `REQUEST_STATUSES`
- `ADDRESS_TYPE_DISPLAYS`
- `RequestCallbackHelper` - генерация callback_data
- `get_text(key, language)` - локализация

---

## 📊 ФИНАЛЬНАЯ ОЦЕНКА

### Complexity Score

| Компонент | Complexity | Risk |
|-----------|-----------|------|
| FSM States Migration | ⭐⭐⭐⭐ | Medium |
| Keyboards Migration | ⭐⭐ | Low |
| Service Integration | ⭐⭐⭐⭐⭐ | High |
| Event Publishing | ⭐⭐⭐ | Medium |
| Testing | ⭐⭐⭐⭐ | High |

### Effort Breakdown

**С командой из 2-3 разработчиков**:

- **Week 1** (5 дней): P0 Critical + половина P1
  - Dev 1: Registration, Verification
  - Dev 2: Onboarding, ProfileEditing, Invites
  - Dev 3: Service clients, testing infrastructure

- **Week 2** (4 дня): P1 завершение + P2 начало
  - Dev 1: Building Selection, Employee Management
  - Dev 2: Shift Management, Time Tracking
  - Dev 3: Integration testing, bug fixes

**Total**: **8-9 рабочих дней** с командой из 2-3 разработчиков

---

## 🚀 РЕКОМЕНДАЦИИ

### Immediate Actions

1. ✅ **Создать GitHub Project** с таблицей всех 14 StatesGroup
2. ✅ **Приоритизировать P0** (Registration, Verification, Onboarding)
3. ✅ **Создать Service Clients** для всех микросервисов
4. ✅ **Настроить testing infrastructure** (pytest-aiogram)

### Code Quality

1. ✅ **Переиспользовать код** из монолита где возможно
2. ✅ **Добавить type hints** везде
3. ✅ **Написать docstrings** для всех функций
4. ✅ **Создать constants файл** для всех текстов/emoji

### Testing Strategy

1. ✅ **Unit tests** для каждого handler
2. ✅ **Integration tests** для service clients
3. ✅ **FSM tests** для каждого StatesGroup
4. ✅ **E2E tests** для критических сценариев

---

**Дата создания**: 7 октября 2025  
**Версия**: 1.0  
**Автор**: Claude AI (Anthropic)  
**Источник**: Полный анализ uk_management_bot/  
**Следующий шаг**: Начать Phase 1 (P0 Critical Blockers)

