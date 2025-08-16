# Telegram Bot для Управляющей Компании

Бот для управления заявками жителей с поддержкой ролей, смен, уведомлений и интеграцией с Google Sheets.

## 🚀 Возможности

- **Система ролей**: Заявитель, Исполнитель, Менеджер
- **Управление заявками**: Создание, отслеживание, изменение статусов
- **Система смен**: Принятие/сдача смен для исполнителей
- **Уведомления**: Автоматические уведомления в каналы
- **Оценки**: Система оценок и отзывов
- **Локализация**: Поддержка русского и узбекского языков
- **Интеграция**: Google Sheets для экспорта данных
- **Дашборд**: Веб-интерфейс для менеджеров

## 📋 Требования

- Python 3.11+
- SQLite (для разработки) / PostgreSQL (для продакшена)
- Telegram Bot Token
- Google Sheets API (опционально)

## 🛠️ Установка

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd uk_management_bot
```

2. **Создайте виртуальное окружение:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

3. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

4. **Настройте конфигурацию:**
```bash
cp .env.example .env
# Отредактируйте .env файл
```

5. **Создайте базу данных:**
```bash
python main.py
```

## ⚙️ Конфигурация

Создайте файл `.env` со следующими переменными:

```env
# Telegram Bot
BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=@your_channel_id

# Database
DATABASE_URL=sqlite:///uk_management.db

# Google Sheets (опционально)
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id

# Application
DEBUG=True
LOG_LEVEL=INFO

# Admin
ADMIN_USER_IDS=123456789,987654321
```

## 🚀 Запуск

```bash
python main.py
```

## 📁 Структура проекта

```
uk_management_bot/
├── config/          # Конфигурация и настройки
├── database/        # Модели БД и сессии
├── handlers/        # Обработчики команд
├── keyboards/       # Клавиатуры
├── middlewares/     # Middleware
├── services/        # Бизнес-логика
├── utils/           # Утилиты
├── admin/           # Админ-панель
├── dashboard/       # Дашборд
├── integrations/    # Интеграции
└── main.py         # Точка входа
```

## 🔧 Разработка

### Этапы разработки:

1. **Этап 1**: Базовая структура и авторизация ✅
2. **Этап 2**: Система заявок (в разработке)
3. **Этап 3**: Система смен и уведомлений
4. **Этап 4**: Оценки и админ-панель
5. **Этап 5**: Интеграции и дашборд

### Добавление новых функций:

1. Создайте обработчик в `handlers/`
2. Добавьте клавиатуры в `keyboards/`
3. Создайте сервис в `services/`
4. Обновите модели БД при необходимости
5. Добавьте тесты

## 📊 База данных

Основные таблицы:
- `users` - Пользователи и роли
- `requests` - Заявки
- `shifts` - Смены
- `ratings` - Оценки
- `audit_logs` - Аудит

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте feature branch
3. Внесите изменения
4. Добавьте тесты
5. Создайте Pull Request

## 📄 Лицензия

MIT License

## 📞 Поддержка

По вопросам обращайтесь к разработчикам проекта.
