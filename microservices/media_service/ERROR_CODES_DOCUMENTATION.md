# ДОКУМЕНТАЦИЯ ПО СИСТЕМЕ КОДОВ ОШИБОК MEDIA SERVICE

## 📋 ОБЗОР

Media Service использует структурированную систему кодов ошибок для обеспечения понятных и информативных сообщений об ошибках. Каждая ошибка имеет уникальный код, описание и категорию.

## 🔢 СТРУКТУРА КОДОВ ОШИБОК

Коды ошибок имеют формат: `MEDIA_XXX`

Где:
- `MEDIA` - префикс сервиса
- `XXX` - трехзначный номер ошибки

### Категории ошибок:

| Префикс | Категория | Диапазон |
|---------|-----------|----------|
| MEDIA_0XX | Общие ошибки | 001-099 |
| MEDIA_1XX | Ошибки загрузки файлов | 100-199 |
| MEDIA_2XX | Ошибки Telegram | 200-299 |
| MEDIA_3XX | Ошибки базы данных | 300-399 |
| MEDIA_4XX | Ошибки поиска | 400-499 |
| MEDIA_5XX | Ошибки дубликатов | 500-599 |
| MEDIA_6XX | Ошибки аутентификации | 600-699 |
| MEDIA_7XX | Ошибки конфигурации | 700-799 |
| MEDIA_8XX | Ошибки сети | 800-899 |
| MEDIA_9XX | Ошибки файловой системы | 900-999 |

## 📊 СПРАВОЧНИК КОДОВ ОШИБОК

### 🔴 ОБЩИЕ ОШИБКИ (MEDIA_0XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_001 | Internal Server Error | Внутренняя ошибка сервера | 500 |
| MEDIA_002 | Validation Error | Ошибка валидации данных | 422 |
| MEDIA_003 | Permission Denied | Доступ запрещен | 403 |
| MEDIA_004 | Resource Not Found | Ресурс не найден | 404 |
| MEDIA_005 | Rate Limit Exceeded | Превышен лимит запросов | 429 |

### 📁 ОШИБКИ ЗАГРУЗКИ ФАЙЛОВ (MEDIA_1XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_101 | File Upload Failed | Ошибка загрузки файла | 400 |
| MEDIA_102 | Invalid File Type | Неподдерживаемый тип файла | 400 |
| MEDIA_103 | File Too Large | Файл слишком большой | 413 |
| MEDIA_104 | File Corrupted | Поврежденный файл | 400 |
| MEDIA_105 | File Processing Error | Ошибка обработки файла | 500 |
| MEDIA_106 | Storage Quota Exceeded | Превышена квота хранилища | 507 |

### 📱 ОШИБКИ TELEGRAM (MEDIA_2XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_201 | Telegram Upload Failed | Ошибка загрузки в Telegram | 502 |
| MEDIA_202 | Telegram API Error | Ошибка API Telegram | 502 |
| MEDIA_203 | Telegram Channel Not Found | Telegram канал не найден | 404 |
| MEDIA_204 | Telegram Bot Token Invalid | Неверный токен бота | 401 |
| MEDIA_205 | Telegram Rate Limit | Превышен лимит Telegram API | 429 |

### 🗄️ ОШИБКИ БАЗЫ ДАННЫХ (MEDIA_3XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_301 | Database Connection Error | Ошибка подключения к БД | 500 |
| MEDIA_302 | Database Query Error | Ошибка запроса к БД | 500 |
| MEDIA_303 | Duplicate Record | Дублирующаяся запись | 409 |
| MEDIA_304 | Constraint Violation | Нарушение ограничения БД | 400 |
| MEDIA_305 | Transaction Failed | Ошибка транзакции | 500 |

### 🔍 ОШИБКИ ПОИСКА (MEDIA_4XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_401 | Invalid Search Query | Некорректный поисковый запрос | 400 |
| MEDIA_402 | Invalid Date Range | Некорректный диапазон дат | 400 |
| MEDIA_403 | Invalid Category | Некорректная категория | 400 |
| MEDIA_404 | Invalid Tags Format | Некорректный формат тегов | 400 |
| MEDIA_405 | Search Timeout | Таймаут поиска | 408 |

### 🔄 ОШИБКИ ДУБЛИКАТОВ (MEDIA_5XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_501 | Duplicate File Detected | Обнаружен дубликат файла | 409 |
| MEDIA_502 | Duplicate Check Failed | Ошибка проверки дубликатов | 500 |
| MEDIA_503 | Duplicate Policy Violation | Нарушение политики дубликатов | 409 |
| MEDIA_504 | Hash Calculation Error | Ошибка вычисления хеша | 500 |

### 🔐 ОШИБКИ АУТЕНТИФИКАЦИИ (MEDIA_6XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_601 | Unauthorized | Не авторизован | 401 |
| MEDIA_602 | Token Expired | Токен истек | 401 |
| MEDIA_603 | Invalid Token | Неверный токен | 401 |
| MEDIA_604 | User Not Found | Пользователь не найден | 404 |

### ⚙️ ОШИБКИ КОНФИГУРАЦИИ (MEDIA_7XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_701 | Missing Config | Отсутствует конфигурация | 500 |
| MEDIA_702 | Invalid Config | Некорректная конфигурация | 500 |
| MEDIA_703 | Service Unavailable | Сервис недоступен | 503 |

### 🌐 ОШИБКИ СЕТИ (MEDIA_8XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_801 | Network Timeout | Таймаут сети | 408 |
| MEDIA_802 | Network Connection Error | Ошибка сетевого соединения | 502 |
| MEDIA_803 | DNS Resolution Error | Ошибка разрешения DNS | 502 |

### 💾 ОШИБКИ ФАЙЛОВОЙ СИСТЕМЫ (MEDIA_9XX)

| Код | Название | Описание | HTTP Статус |
|-----|----------|----------|-------------|
| MEDIA_901 | File Not Found | Файл не найден | 404 |
| MEDIA_902 | File Access Denied | Доступ к файлу запрещен | 403 |
| MEDIA_903 | Disk Space Insufficient | Недостаточно места на диске | 507 |
| MEDIA_904 | File Locked | Файл заблокирован | 423 |

## 📝 ФОРМАТ ОТВЕТА ОБ ОШИБКЕ

```json
{
  "error_code": "MEDIA_102",
  "message": "Неподдерживаемый тип файла",
  "description": "Данный тип файла не поддерживается системой",
  "category": "Ошибки загрузки файлов",
  "details": {
    "file_type": "text/plain",
    "allowed_types": ["image/jpeg", "image/png", "image/gif"],
    "filename": "document.txt"
  }
}
```

### Поля ответа:

- **error_code** (string) - Уникальный код ошибки
- **message** (string) - Краткое сообщение об ошибке
- **description** (string) - Подробное описание ошибки
- **category** (string) - Категория ошибки
- **details** (object, optional) - Дополнительные детали ошибки

## 🛠️ ИСПОЛЬЗОВАНИЕ В КОДЕ

### Создание исключения с кодом ошибки:

```python
from app.core.exceptions import InvalidFileType

raise InvalidFileType(
    details={
        "file_type": "text/plain",
        "allowed_types": ["image/jpeg", "image/png"],
        "filename": "document.txt"
    }
)
```

### Создание кастомного исключения:

```python
from app.core.exceptions import MediaHTTPException
from app.core.error_codes import MediaErrorCode

raise MediaHTTPException(
    error_code=MediaErrorCode.INVALID_FILE_TYPE,
    status_code=400,
    details={"custom": "data"}
)
```

## 🌍 МНОГОЯЗЫЧНОСТЬ

Система поддерживает несколько языков для сообщений об ошибках:

```python
from app.core.error_codes import MediaErrorMessages

# Русский (по умолчанию)
message_ru = MediaErrorMessages.get_message(MediaErrorCode.INVALID_FILE_TYPE, "ru")

# Английский
message_en = MediaErrorMessages.get_message(MediaErrorCode.INVALID_FILE_TYPE, "en")
```

## 📊 МОНИТОРИНГ И ЛОГИРОВАНИЕ

Все ошибки логируются с указанием:
- Кода ошибки
- Времени возникновения
- Контекста выполнения
- Детальной информации

### Пример лога:

```
2025-10-06 16:22:23,389 - app.api.v1.media - ERROR - MEDIA_102: Invalid file type 'text/plain' for upload. Allowed: ['image/jpeg', 'image/png']
```

## 🔧 КОНФИГУРАЦИЯ

Система кодов ошибок настраивается через:

- `app/core/error_codes.py` - Определение кодов и сообщений
- `app/core/exceptions.py` - HTTP исключения
- `app/schemas/media.py` - Схемы ответов об ошибках

## 📈 РАСШИРЕНИЕ СИСТЕМЫ

Для добавления новых кодов ошибок:

1. Добавьте новый код в `MediaErrorCode` enum
2. Добавьте сообщения в `MediaErrorMessages.ERROR_MESSAGES`
3. Создайте соответствующее исключение в `exceptions.py`
4. Обновите документацию

## ✅ ПРЕИМУЩЕСТВА

- **Стандартизация** - Единый формат для всех ошибок
- **Информативность** - Подробные описания и детали
- **Отладка** - Легкая идентификация проблем
- **Мониторинг** - Структурированное логирование
- **Интеграция** - Понятные коды для внешних систем
- **Многоязычность** - Поддержка нескольких языков

## 🎯 РЕКОМЕНДАЦИИ ПО ИСПОЛЬЗОВАНИЮ

1. **Всегда используйте коды ошибок** вместо произвольных сообщений
2. **Добавляйте детали** для упрощения отладки
3. **Логируйте ошибки** с полным контекстом
4. **Документируйте новые коды** в этом справочнике
5. **Тестируйте обработку ошибок** в автоматических тестах

---

**Версия документации:** 1.0.0  
**Дата обновления:** 6 октября 2025  
**Автор:** Media Service Development Team
