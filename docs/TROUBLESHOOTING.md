# 🔧 Устранение неполадок

> _Последнее редактирование: 2025-09-26_

## 🚨 Критические проблемы

### Бот не запускается

#### Симптомы:
- Бот не отвечает на команды
- Ошибки в логах при запуске
- Контейнер Docker не запускается

#### Решения:

**1. Проверьте переменные окружения**
```bash
# Проверьте наличие обязательных переменных
echo $BOT_TOKEN
echo $DATABASE_URL
echo $REDIS_URL

# Если переменные не установлены, создайте .env файл
cp env.example .env
# Отредактируйте .env файл с правильными значениями
```

**2. Проверьте подключение к базе данных**
```bash
# Для PostgreSQL
docker exec uk-management-bot-dev psql $DATABASE_URL -c "SELECT 1;"

# Для SQLite
docker exec uk-management-bot-dev sqlite3 uk_management_bot.db "SELECT 1;"
```

**3. Проверьте подключение к Redis**
```bash
docker exec uk-management-bot-dev redis-cli ping
```

**4. Проверьте логи приложения**
```bash
docker logs uk-management-bot-dev
```

### Ошибки базы данных

#### Симптомы:
- Ошибки "table does not exist"
- Ошибки миграций
- Проблемы с подключением

#### Решения:

**1. Примените миграции**
```bash
docker exec uk-management-bot-dev python -m alembic upgrade head
```

**2. Проверьте статус миграций**
```bash
docker exec uk-management-bot-dev python -m alembic current
docker exec uk-management-bot-dev python -m alembic history
```

**3. Сбросьте базу данных (только для разработки)**
```bash
# Удалите все таблицы
docker exec uk-management-bot-dev python -m alembic downgrade base

# Примените миграции заново
docker exec uk-management-bot-dev python -m alembic upgrade head
```

**4. Проверьте права доступа к базе данных**
```bash
# Для PostgreSQL
docker exec uk-management-bot-dev psql $DATABASE_URL -c "\du"
```

## ⚠️ Проблемы с пользователями

### Пользователь не может войти в систему

#### Симптомы:
- Пользователь не получает доступ к функциям
- Ошибки "Access denied"
- Пользователь не видит свои заявки

#### Решения:

**1. Проверьте роль пользователя**
```sql
-- В базе данных
SELECT id, first_name, last_name, roles FROM users WHERE telegram_id = <user_id>;
```

**2. Проверьте права доступа**
```python
# В коде проверьте middleware
from uk_management_bot.middlewares.auth import AuthMiddleware
```

**3. Сбросьте состояние пользователя**
```bash
# Очистите Redis кэш для пользователя
docker exec uk-management-bot-dev redis-cli DEL "user_state:<user_id>"
```

### Проблемы с назначениями заявок

#### Симптомы:
- Заявки не отображаются у исполнителей
- Ошибки при назначении заявок
- Дублирование назначений

#### Решения:

**1. Проверьте назначения в базе данных**
```sql
-- Проверьте все назначения
SELECT r.id, r.title, a.assignment_type, a.specialization, a.status 
FROM requests r 
JOIN assignments a ON r.id = a.request_id;

-- Проверьте назначения конкретного исполнителя
SELECT r.id, r.title, a.assignment_type, a.status 
FROM requests r 
JOIN assignments a ON r.id = a.request_id 
WHERE a.executor_id = <executor_id>;
```

**2. Проверьте статус заявки**
```sql
-- Статус должен быть "В работе" для отображения у исполнителя
SELECT id, title, status FROM requests WHERE id = <request_id>;
```

**3. Очистите некорректные назначения**
```sql
-- Отмените все назначения заявки
UPDATE assignments SET status = 'cancelled' WHERE request_id = <request_id>;

-- Создайте новое назначение
INSERT INTO assignments (request_id, executor_id, assignment_type, status, assigned_by) 
VALUES (<request_id>, <executor_id>, 'individual', 'active', <manager_id>);
```

## 🔄 Проблемы с состоянием FSM

### Пользователь застрял в процессе

#### Симптомы:
- Бот не отвечает на команды
- Пользователь не может выйти из процесса
- Ошибки "Invalid state"

#### Решения:

**1. Сбросьте состояние пользователя**
```bash
# Очистите состояние в Redis
docker exec uk-management-bot-dev redis-cli DEL "fsm:<user_id>"
```

**2. Отправьте команду сброса**
```python
# В коде добавьте обработчик
@router.message(commands=['reset'])
async def reset_state(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Состояние сброшено. Используйте /start для начала работы.")
```

**3. Проверьте логи FSM**
```bash
# Включите отладочное логирование
export LOG_LEVEL=DEBUG
docker restart uk-management-bot-dev
```

## 📱 Проблемы с Telegram API

### Ошибки отправки сообщений

#### Симптомы:
- Сообщения не доставляются
- Ошибки "Bot was blocked by the user"
- Ошибки "Chat not found"

#### Решения:

**1. Проверьте токен бота**
```bash
# Проверьте токен через API
curl "https://api.telegram.org/bot<BOT_TOKEN>/getMe"
```

**2. Проверьте права бота**
- Убедитесь, что бот не заблокирован пользователем
- Проверьте, что бот добавлен в группу (если используется)
- Убедитесь, что у бота есть права на отправку сообщений

**3. Обработайте ошибки в коде**
```python
try:
    await bot.send_message(user_id, message)
except TelegramForbiddenError:
    logger.warning(f"User {user_id} blocked the bot")
except TelegramBadRequest as e:
    logger.error(f"Telegram API error: {e}")
```

### Проблемы с callback-запросами

#### Симптомы:
- Кнопки не работают
- Ошибки "Callback query is too old"
- Неправильная обработка callback

#### Решения:

**1. Проверьте обработчики callback**
```python
# Убедитесь, что callback обрабатывается
@router.callback_query(lambda c: c.data.startswith("assign_request_"))
async def handle_assign_request(callback: CallbackQuery, state: FSMContext):
    try:
        # Обработка
        await callback.answer("Обработано")
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback.answer("Произошла ошибка")
```

**2. Проверьте timeout callback**
```python
# Увеличьте timeout если необходимо
@router.callback_query(lambda c: c.data.startswith("assign_request_"))
async def handle_assign_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Обрабатывается...", show_alert=False)
    # Долгая обработка
```

## 🧪 Проблемы с тестированием

### Тесты не проходят

#### Симптомы:
- Ошибки в тестах
- Проблемы с моками
- Ошибки импорта

#### Решения:

**1. Проверьте зависимости тестов**
```bash
# Установите зависимости для тестирования
pip install -r requirements-dev.txt
```

**2. Запустите тесты с подробным выводом**
```bash
docker exec uk-management-bot-dev python -m pytest tests/ -v -s
```

**3. Проверьте конфигурацию тестов**
```python
# В conftest.py убедитесь, что моки настроены правильно
@pytest.fixture
def mock_db():
    return Mock()
```

**4. Запустите отдельные тесты**
```bash
# Запустите конкретный тест
docker exec uk-management-bot-dev python -m pytest tests/test_request_assignment_system.py::TestAssignmentService::test_assign_to_group -v
```

## 🔍 Диагностика

### Команды для диагностики

**1. Проверка состояния системы**
```bash
# Статус контейнеров
docker ps

# Логи приложения
docker logs uk-management-bot-dev

# Использование ресурсов
docker stats uk-management-bot-dev
```

**2. Проверка базы данных**
```bash
# Подключение к базе
docker exec -it uk-management-bot-dev psql $DATABASE_URL

# Проверка таблиц
\dt

# Проверка данных
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM requests;
SELECT COUNT(*) FROM assignments;
```

**3. Проверка Redis**
```bash
# Подключение к Redis
docker exec -it uk-management-bot-dev redis-cli

# Проверка ключей
KEYS *

# Проверка памяти
INFO memory
```

**4. Проверка сети**
```bash
# Проверка подключений
docker exec uk-management-bot-dev ping google.com

# Проверка портов
docker exec uk-management-bot-dev netstat -tulpn
```

### Логирование

**1. Включение отладочного режима**
```bash
export LOG_LEVEL=DEBUG
docker restart uk-management-bot-dev
```

**2. Просмотр логов в реальном времени**
```bash
docker logs -f uk-management-bot-dev
```

**3. Фильтрация логов**
```bash
# Логи ошибок
docker logs uk-management-bot-dev 2>&1 | grep ERROR

# Логи конкретного пользователя
docker logs uk-management-bot-dev 2>&1 | grep "user_id:123456"
```

## 🆘 Получение помощи

### Когда обращаться к администратору

- Критические ошибки системы
- Проблемы с безопасностью
- Потеря данных
- Проблемы производительности
- Ошибки в бизнес-логике

### Информация для предоставления

При обращении за помощью предоставьте:
1. Описание проблемы
2. Шаги для воспроизведения
3. Логи ошибок
4. Версию системы
5. Конфигурацию окружения

### Контакты

- **Техническая поддержка**: @admin_username
- **Документация**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)

---

**Последнее обновление**: 30 августа 2025  
**Версия**: 1.0
