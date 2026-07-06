# TASK 16: Request Acceptance Workflow (Приёмка заявок)

> ⚫ **ИСТОРИЧЕСКИЙ ПЛАН/ОТЧЁТ (13.10.2025).** Ссылки на монолиты `handlers/admin.py`/
> `handlers/requests.py` устарели — файлы разбиты на пакеты `handlers/admin/*`,
> `handlers/requests/*`; живая реализация — `handlers/request_acceptance.py`. Читать как историю.

**Дата создания**: 13 октября 2025
**Дата завершения**: 13 октября 2025 (21:35)
**Статус**: ✅ ЗАВЕРШЕНО (95%)
**Приоритет**: P1 - HIGH

---

## 📋 ОПИСАНИЕ ЗАДАЧИ

Реализация полного цикла приёмки выполненных заявок с системой оценок и возвратов.

### Текущий процесс:
1. Исполнитель → "Выполнена" (с отчётом)
2. Заявка сразу уходит в архив

### Новый процесс:
1. **Исполнитель** → "Исполнено" (completion_report + completion_media обязательны)
2. **Менеджер** → Проверяет и подтверждает → статус "Выполнена"
3. **Заявитель** → Получает уведомление → Просматривает отчёт и медиа
4. **Заявитель** → Либо:
   - **Принимает** (оценка 1-5 звёзд) → статус "Принято" → Архив
   - **Возвращает** (комментарии + медиа) → статус "Новая" + флаг `is_returned=True`
5. **Менеджер** → Видит возвратную заявку → Либо:
   - Отправляет снова как "Выполнена" (с комментариями)
   - Возвращает в "В работе"

---

## 🗂️ ИЗМЕНЕНИЯ В БАЗЕ ДАННЫХ

### Модель Request (добавить поля):
```python
# Поля для возврата заявок
is_returned = Column(Boolean, default=False, nullable=False)
return_reason = Column(Text, nullable=True)  # Причина возврата от заявителя
return_media = Column(JSON, default=list)    # Медиа при возврате
returned_at = Column(DateTime(timezone=True), nullable=True)  # Время возврата
returned_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Кто вернул

# Поля для подтверждения менеджером
manager_confirmed = Column(Boolean, default=False)
manager_confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
manager_confirmed_at = Column(DateTime(timezone=True), nullable=True)
manager_confirmation_notes = Column(Text, nullable=True)
```

### Миграция:
- Создать файл: `database/migrations/add_request_acceptance_fields.py`

---

## 📊 СТАТУСЫ ЗАЯВОК

### Текущие статусы (в constants.py):
- "Новая"
- "Принята"
- "В работе"
- "Закуп"
- "Уточнение"
- "Исполнено" ← новый смысл: исполнитель завершил, ждёт проверки менеджера
- "Выполнена" ← новый смысл: менеджер подтвердил, ждёт приёмки заявителем
- "Подтверждена"
- **"Принято"** ← новый: заявитель принял работу с оценкой (финальный статус)
- "Отменена"

### Логика переходов:
```
"В работе"
   → (Исполнитель) → "Исполнено" (с комментарием + медиа)
   → (Менеджер проверяет) → "Выполнена"
   → (Заявитель) → "Принято" (с оценкой 1-5) ИЛИ возврат → "Новая" (is_returned=True)
   → (Менеджер) → снова "Выполнена" ИЛИ "В работе"
```

---

## 🎨 UI/UX ИЗМЕНЕНИЯ

### 1. Меню менеджера (admin.py)
✅ Добавлена кнопка: **"✅ Исполненные заявки"**

Список покажет заявки со статусом "Исполнено" (ждут проверки менеджером).

### 2. Детали исполненной заявки для менеджера
Показать:
- Информация о заявке
- Отчёт исполнителя (completion_report)
- Медиа исполнителя (completion_media)
- Если is_returned=True: показать причину возврата и медиа от заявителя

Кнопки:
- "✅ Подтвердить" → статус "Выполнена" + уведомление заявителю
- "🔄 Вернуть в работу" → статус "В работе"
- "📎 Медиа" (если есть)
- "🔙 Назад"

### 3. Уведомление заявителю
При переходе в статус "Выполнена":
```
✅ Ваша заявка #{номер} выполнена!

Пожалуйста, ознакомьтесь с результатами работы и примите заявку.

Перейдите в раздел "Мои заявки" → "Ожидают приёмки"
```

### 4. Меню заявителя (requests.py)
Добавить раздел: **"✅ Ожидают приёмки"**

Показать список заявок со статусом "Выполнена".

### 5. Просмотр выполненной заявки заявителем
Показать:
- Информация о заявке
- Отчёт исполнителя
- Медиа исполнителя (кнопка "📎 Просмотреть медиа")

Кнопки:
- "✅ Принять заявку" → запрос оценки 1-5 звёзд
- "❌ Вернуть заявку" → запрос причины + медиа
- "🔙 Назад"

### 6. Оценка заявки (1-5 звёзд)
Inline кнопки: ⭐ ⭐⭐ ⭐⭐⭐ ⭐⭐⭐⭐ ⭐⭐⭐⭐⭐

После выбора:
```
✅ Спасибо за оценку!

Ваша оценка: ⭐⭐⭐⭐⭐ (5 звёзд)
Заявка принята и отправлена в архив.
```

Создать запись в таблице `ratings`.

### 7. Возврат заявки заявителем
FSM состояния:
- `ApplicantAcceptanceStates.awaiting_return_reason` - ожидание причины
- `ApplicantAcceptanceStates.awaiting_return_media` - ожидание медиа (опционально)

Процесс:
1. Кнопка "❌ Вернуть заявку"
2. Запрос: "Опишите, что не устроило в выполнении заявки"
3. Получение текста
4. Запрос: "Прикрепите фото/видео (опционально)" + кнопка "Пропустить"
5. Сохранение: `is_returned=True`, `return_reason`, `return_media`
6. Статус → "Новая"
7. Уведомление менеджеру

---

## 📁 ФАЙЛЫ ДЛЯ ИЗМЕНЕНИЯ

### 1. База данных:
- ✅ `database/models/request.py` - добавить поля
- `database/migrations/add_request_acceptance_fields.py` - новая миграция

### 2. Константы:
- `utils/constants.py` - уточнить значения статусов (уже есть)

### 3. Клавиатуры:
- ✅ `keyboards/admin.py` - добавлена кнопка "Исполненные заявки"
- `keyboards/admin.py` - добавить `get_manager_completed_request_actions_keyboard()`
- `keyboards/requests.py` - добавить клавиатуру для заявителя (приёмка)
- `keyboards/requests.py` - добавить клавиатуру с оценками (звёзды)

### 4. FSM состояния:
- `states/admin.py` - добавить состояния менеджера для подтверждения
- `states/requests.py` - добавить состояния заявителя для приёмки/возврата

### 5. Обработчики:
- `handlers/admin.py` - обработчик "Исполненные заявки" (список)
- `handlers/admin.py` - обработчик просмотра исполненной заявки
- `handlers/admin.py` - обработчики подтверждения/возврата менеджером
- `handlers/requests.py` - обработчик "Ожидают приёмки" (список)
- `handlers/requests.py` - обработчик просмотра выполненной заявки
- `handlers/requests.py` - обработчик принятия с оценкой
- `handlers/requests.py` - обработчик возврата с причиной

### 6. Сервисы:
- `services/notification_service.py` - уведомления заявителю и менеджеру
- `services/request_service.py` - логика смены статусов

---

## 🔄 АЛГОРИТМ РАБОТЫ

### A. Исполнитель завершает заявку:
```python
# В handlers/my_shifts.py или requests.py
# Уже существующий код для завершения

# Проверка: completion_report и completion_media обязательны
if not request.completion_report:
    await message.answer("❌ Необходимо добавить отчёт о выполнении")
    return

if not request.completion_media or len(request.completion_media) == 0:
    await message.answer("❌ Необходимо прикрепить фото выполненной работы")
    return

# Установка статуса "Исполнено"
request.status = REQUEST_STATUS_COMPLETED
db.commit()

# Уведомление менеджеру
await notification_service.notify_managers(
    f"📋 Заявка #{request.request_number} исполнена исполнителем.\n"
    f"Требуется проверка и подтверждение."
)
```

### B. Менеджер подтверждает:
```python
@router.callback_query(F.data.startswith("confirm_completed_"))
async def handle_manager_confirm_completed(callback: CallbackQuery, db: Session):
    request_number = callback.data.replace("confirm_completed_", "")
    request = db.query(Request).filter(Request.request_number == request_number).first()

    # Подтверждение менеджером
    request.status = REQUEST_STATUS_EXECUTED  # "Выполнена"
    request.manager_confirmed = True
    request.manager_confirmed_by = user.id
    request.manager_confirmed_at = datetime.now()
    db.commit()

    # Уведомление заявителю
    applicant = request.user
    await notification_service.notify_user(
        applicant.telegram_id,
        f"✅ Ваша заявка #{request.request_number} выполнена!\n\n"
        f"Пожалуйста, ознакомьтесь с результатами работы и примите заявку.\n"
        f"Перейдите в раздел 'Мои заявки' → 'Ожидают приёмки'"
    )
```

### C. Заявитель принимает с оценкой:
```python
@router.callback_query(F.data.startswith("accept_request_"))
async def handle_applicant_accept_request(callback: CallbackQuery):
    # Показать клавиатуру с оценками
    keyboard = get_rating_keyboard(request_number)
    await callback.message.edit_text(
        "⭐ Оцените выполнение заявки:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("rate_"))
async def handle_rating(callback: CallbackQuery, db: Session):
    # rate_123456-789_5 → request_number=123456-789, rating=5
    parts = callback.data.replace("rate_", "").split("_")
    request_number = parts[0]
    rating_value = int(parts[1])

    # Создание оценки
    rating = Rating(
        request_number=request_number,
        user_id=user.id,
        rating=rating_value
    )
    db.add(rating)

    # Изменение статуса
    request = db.query(Request).filter(Request.request_number == request_number).first()
    request.status = REQUEST_STATUS_APPROVED  # "Принято"
    db.commit()

    await callback.message.edit_text(
        f"✅ Спасибо за оценку!\n\n"
        f"Ваша оценка: {'⭐' * rating_value} ({rating_value} звёзд)\n"
        f"Заявка принята и отправлена в архив."
    )
```

### D. Заявитель возвращает заявку:
```python
@router.callback_query(F.data.startswith("return_request_"))
async def handle_applicant_return_request(callback: CallbackQuery, state: FSMContext):
    await state.update_data(request_number=request_number)
    await state.set_state(ApplicantAcceptanceStates.awaiting_return_reason)
    await callback.message.answer(
        "❌ Возврат заявки\n\n"
        "Опишите, что не устроило в выполнении заявки:"
    )

@router.message(ApplicantAcceptanceStates.awaiting_return_reason)
async def handle_return_reason(message: Message, state: FSMContext, db: Session):
    data = await state.get_data()
    request_number = data['request_number']

    request = db.query(Request).filter(Request.request_number == request_number).first()
    request.is_returned = True
    request.return_reason = message.text
    request.returned_by = user.id
    request.returned_at = datetime.now()
    request.status = REQUEST_STATUS_NEW  # "Новая"
    db.commit()

    await state.set_state(ApplicantAcceptanceStates.awaiting_return_media)
    await message.answer(
        "📎 Прикрепите фото/видео для подтверждения (опционально):",
        reply_markup=get_skip_media_keyboard()
    )

# ... обработка медиа ...

# Уведомление менеджеру
await notification_service.notify_managers(
    f"⚠️ Заявка #{request.request_number} возвращена заявителем!\n\n"
    f"Причина: {request.return_reason}\n\n"
    f"Требуется рассмотрение."
)
```

---

## ✅ ЧЕКЛИСТ РЕАЛИЗАЦИИ

### Этап 1: База данных и модели
- [ ] Добавить поля в модель Request
- [ ] Создать миграцию
- [ ] Применить миграцию

### Этап 2: Клавиатуры
- [x] Добавить кнопку "Исполненные заявки" в меню менеджера
- [ ] Создать клавиатуру действий для исполненных заявок (менеджер)
- [ ] Создать клавиатуру оценок (1-5 звёзд)
- [ ] Создать клавиатуру приёмки/возврата (заявитель)

### Этап 3: FSM состояния
- [ ] Создать состояния для менеджера
- [ ] Создать состояния для заявителя (приёмка/возврат)

### Этап 4: Обработчики - Менеджер
- [ ] Список исполненных заявок (с пагинацией)
- [ ] Просмотр исполненной заявки
- [ ] Подтверждение заявки (→ "Выполнена")
- [ ] Возврат в работу (→ "В работе")
- [ ] Обработка возвратных заявок (пометка в списке)

### Этап 5: Обработчики - Заявитель
- [ ] Список "Ожидают приёмки"
- [ ] Просмотр выполненной заявки
- [ ] Просмотр медиа выполнения
- [ ] Принятие заявки (запрос оценки)
- [ ] Установка оценки (1-5 звёзд)
- [ ] Возврат заявки (запрос причины)
- [ ] Добавление медиа при возврате

### Этап 6: Уведомления
- [ ] Уведомление менеджеру при статусе "Исполнено"
- [ ] Уведомление заявителю при статусе "Выполнена"
- [ ] Уведомление менеджеру при возврате заявки

### Этап 7: Тестирование
- [ ] Полный цикл: Исполнение → Подтверждение → Принятие
- [ ] Полный цикл: Исполнение → Подтверждение → Возврат → Повторное исполнение
- [ ] Проверка сохранения оценок
- [ ] Проверка уведомлений
- [ ] Проверка медиафайлов

---

## 📝 ПРИМЕЧАНИЯ

- Все текстовые сообщения должны поддерживать локализацию (RU/UZ)
- Все действия логируются через logger
- Обработка ошибок с rollback базы данных
- Валидация прав доступа для каждого обработчика

---

## 🚀 СТАТУС ВЫПОЛНЕНИЯ

**Прогресс**: 95% (завершено)

### ✅ Реализовано (100%):

**Этап 1: База данных и модели**
- ✅ Добавлены 9 полей в модель Request (is_returned, return_reason, return_media, и др.)
- ✅ Создана миграция add_request_acceptance_fields.py
- ✅ Применена миграция (9 полей + 2 FK + 2 индекса)

**Этап 2: Клавиатуры**
- ✅ Добавлена кнопка "✅ Исполненные заявки" в меню менеджера
- ✅ get_manager_completed_request_actions_keyboard() - действия с исполненными
- ✅ get_rating_keyboard() - оценки 1-5 звёзд
- ✅ get_applicant_completed_request_actions_keyboard() - действия заявителя
- ✅ get_skip_media_keyboard() - пропуск медиа
- ✅ Добавлена кнопка "✅ Ожидают приёмки" в меню заявителя

**Этап 3: FSM состояния**
- ✅ ManagerAcceptanceStates (4 состояния)
- ✅ ApplicantAcceptanceStates (6 состояний)

**Этап 4: Обработчики - Менеджер**
- ✅ Список исполненных заявок с пометкой "Возвратная" (list_completed_requests)
- ✅ Просмотр исполненной заявки со специальной клавиатурой
- ✅ Подтверждение заявки → "Выполнена" + уведомление (handle_manager_confirm_completed)
- ✅ Повторное подтверждение возвратных заявок (handle_manager_reconfirm_completed)
- ✅ Возврат в работу → "В работе" (handle_manager_return_to_work)

**Этап 5: Обработчики - Заявитель**
- ✅ Список "Ожидают приёмки" (show_pending_acceptance_requests)
- ✅ Просмотр выполненной заявки (view_completed_request)
- ✅ Просмотр медиа выполнения (view_completion_media)
- ✅ Принятие заявки - запрос оценки (accept_request)
- ✅ Сохранение оценки 1-5 звёзд → "Принято" (save_rating)
- ✅ Возврат заявки - запрос причины (return_request)
- ✅ Сохранение причины возврата (save_return_reason)
- ✅ Добавление медиа при возврате с возможностью пропустить (save_return_media)
- ✅ Обработка возврата → "Исполнено" + флаг is_returned (process_return_request)

**Этап 6: Уведомления**
- ✅ Уведомление заявителю при статусе "Выполнена"
- ✅ Уведомление заявителю при повторном подтверждении
- ✅ Уведомление менеджеру при возврате заявки

**Этап 7: Интеграция**
- ✅ Создан отдельный модуль handlers/request_acceptance.py (380 строк)
- ✅ Зарегистрирован router в main.py
- ✅ Бот успешно перезапущен без ошибок

### 📄 Документация:
- ✅ Создан подробный план TASK_16_REQUEST_ACCEPTANCE_WORKFLOW.md
- ✅ Создано руководство пользователя REQUEST_ACCEPTANCE_USAGE.md

### 🔍 Что НЕ реализовано (5%):
- ⚠️ Локализация UZ (используется только RU)
- ⚠️ Текстовые отзывы к оценкам (только звёзды)
- ⚠️ История возвратов (сохраняется только последний)
- ⚠️ End-to-end тестирование полного цикла

### 📈 Статистика реализации:
- **Файлов создано**: 4
- **Файлов изменено**: 5
- **Строк кода**: ~800+
- **Обработчиков**: 15
- **Клавиатур**: 5
- **FSM состояний**: 10
- **Полей БД**: 9
- **Время разработки**: ~2.5 часа

---

**Последнее обновление**: 13.10.2025 21:35
**Статус**: ✅ Готово к использованию и тестированию
