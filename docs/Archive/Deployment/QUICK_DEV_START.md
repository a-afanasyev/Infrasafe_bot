# 🚀 Быстрый старт для разработки

> _Последнее редактирование: 2025-10-29_

## 📋 Команды для работы

### Запуск development окружения
```bash
# Остановить production (если запущен)
docker-compose down

# Запустить development
docker-compose -f docker-compose.dev.yml up -d

# Посмотреть логи
docker-compose -f docker-compose.dev.yml logs -f app
```

### Hot-Reload (изменения без пересборки)
```bash
# Вносите изменения в код в папке uk_management_bot/
# Затем перезапускайте только приложение:
docker-compose -f docker-compose.dev.yml restart app
```

### Остановка
```bash
docker-compose -f docker-compose.dev.yml down
```

## 🔧 Что работает

✅ **Код монтируется как volume** - изменения применяются без пересборки  
✅ **База данных PostgreSQL** - с автоматической инициализацией  
✅ **Redis** - для rate limiting  
✅ **Миграция данных** - из SQLite в PostgreSQL выполнена  
✅ **Логирование** - DEBUG уровень для разработки  

## 📊 Данные в базе

- **2 пользователя** (мигрированы из SQLite)
- **15 заявок** (мигрированы из SQLite)
- **36 записей аудита** (мигрированы из SQLite)

## 🎯 Готово к разработке!

Бот работает и готов к тестированию. Пишите в Telegram! 🚀
