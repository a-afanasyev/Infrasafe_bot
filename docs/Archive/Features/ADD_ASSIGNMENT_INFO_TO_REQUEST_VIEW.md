# Добавление: Информация о назначении в просмотре заявки

**Дата**: 16 октября 2025
**Статус**: ✅ Реализовано

## Описание

При просмотре деталей заявки менеджером добавлена информация о том, кому назначена заявка:
- Конкретный исполнитель (индивидуальное назначение)
- Дежурный специалист с указанием специализации (групповое назначение)

## Было

```
📋 Заявка #251016-012

👤 Заявитель: Andrey Afanasyev
📱 Telegram ID: 48617336
📂 Категория: Отопление
📊 Статус: В работе
📍 Адрес: Дом: Yangi Olmazor, 14V
📝 Описание: фывфывфывфывфывфыв
⚡ Срочность: Срочная
📅 Создана: 16.10.2025 10:05
🔄 Обновлена: 16.10.2025 10:20
```

## Стало

### Для индивидуального назначения:

```
📋 Заявка #251016-012

👤 Заявитель: Andrey Afanasyev
📱 Telegram ID: 48617336
📂 Категория: Отопление
📊 Статус: В работе
📍 Адрес: Дом: Yangi Olmazor, 14V
📝 Описание: фывфывфывфывфывфыв
⚡ Срочность: Срочная
📅 Создана: 16.10.2025 10:05
🔄 Обновлена: 16.10.2025 10:20
👤 Назначено: Andrey Afanasyev  ← ДОБАВЛЕНО
```

### Для группового назначения:

```
📋 Заявка #251016-012

👤 Заявитель: Andrey Afanasyev
📱 Telegram ID: 48617336
📂 Категория: Отопление
📊 Статус: В работе
📍 Адрес: Дом: Yangi Olmazor, 14V
📝 Описание: фывфывфывфывфывфыв
⚡ Срочность: Срочная
📅 Создана: 16.10.2025 10:05
🔄 Обновлена: 16.10.2025 10:20
👥 Назначено: Дежурный специалист (HVAC/Отопление)  ← ДОБАВЛЕНО
```

## Реализация

### Файл: `admin.py`

Функция: `handle_manager_view_request()` (строки 242-360)

**Изменения** (строки 290-320):

```python
# Добавляем информацию о назначении
from uk_management_bot.database.models.request_assignment import RequestAssignment
active_assignment = db.query(RequestAssignment).filter(
    RequestAssignment.request_number == request.request_number,
    RequestAssignment.status == "active"
).first()

if active_assignment:
    if active_assignment.assignment_type == "group":
        # Групповое назначение (дежурному специалисту)
        specialization_names = {
            "plumber": "Сантехник",
            "electrician": "Электрик",
            "landscaping": "Благоустройство",
            "cleaning": "Уборка",
            "security": "Охрана",
            "repair": "Ремонт",
            "installation": "Установка",
            "maintenance": "Обслуживание",
            "hvac": "HVAC/Отопление"
        }
        spec_name = specialization_names.get(
            active_assignment.group_specialization, 
            active_assignment.group_specialization
        )
        message_text += f"👥 Назначено: Дежурный специалист ({spec_name})\n"
        
    elif active_assignment.assignment_type == "individual" and active_assignment.executor_id:
        # Индивидуальное назначение конкретному исполнителю
        assigned_executor = db.query(User).filter(
            User.id == active_assignment.executor_id
        ).first()
        if assigned_executor:
            executor_name = f"{assigned_executor.first_name or ''} {assigned_executor.last_name or ''}".strip()
            if not executor_name:
                executor_name = f"@{assigned_executor.username}" if assigned_executor.username else f"ID{assigned_executor.id}"
            message_text += f"👤 Назначено: {executor_name}\n"
```

## Логика работы

1. **Запрос к таблице `request_assignments`**:
   - Ищется активное назначение для заявки (`status = 'active'`)
   - Если найдено - показывается информация

2. **Групповое назначение** (`assignment_type = 'group'`):
   - Показывается специализация из `group_specialization`
   - Используется маппинг для перевода на русский
   - Формат: `👥 Назначено: Дежурный специалист (Специализация)`

3. **Индивидуальное назначение** (`assignment_type = 'individual'`):
   - Запрашивается информация об исполнителе по `executor_id`
   - Формируется полное имя (first_name + last_name)
   - Если имени нет - используется username или ID
   - Формат: `👤 Назначено: Имя Фамилия`

4. **Нет назначения**:
   - Если `active_assignment` не найдено - строка не добавляется
   - Заявка может быть без назначения (статус "Новая")

## Маппинг специализаций

```python
specialization_names = {
    "plumber": "Сантехник",
    "electrician": "Электрик",
    "landscaping": "Благоустройство",
    "cleaning": "Уборка",
    "security": "Охрана",
    "repair": "Ремонт",
    "installation": "Установка",
    "maintenance": "Обслуживание",
    "hvac": "HVAC/Отопление"
}
```

## Преимущества

1. ✅ Менеджер сразу видит, кому назначена заявка
2. ✅ Для групповых назначений видна специализация
3. ✅ Для индивидуальных назначений - конкретный исполнитель
4. ✅ Информация актуальна (берётся из `request_assignments`)
5. ✅ Не показывается для не назначенных заявок

## Возможные улучшения

1. Добавить дату назначения (`created_at` из `request_assignments`)
2. Показывать, кто назначил (`created_by`)
3. Для групповых - показывать количество исполнителей в смене
4. История назначений (если заявка переназначалась)

## Связанные файлы

- ✅ [admin.py:290-320](uk_management_bot/handlers/admin.py#L290) - добавлена логика отображения

---

**Автор**: Claude Code (Sonnet 4.5)
**Дата**: 16 октября 2025, 10:27 UTC
**Статус**: ✅ **РЕАЛИЗОВАНО**
