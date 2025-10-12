# 🔧 Error Handling Fix - HTTP Status Codes

## 📅 Дата: 6 октября 2025

---

## 🎯 Проблема

### Симптом
```
POST http://localhost:8004/api/v1/media/upload
500 (Internal Server Error)
```

### Реальная причина
Пользователь пытался загрузить файл типа `image/svg+xml`, который не входит в список разрешённых типов файлов.

### Техническая проблема
Код валидации корректно выбрасывал `HTTPException(status_code=400)`, но обработчик ошибок ловил **ВСЕ** исключения (включая HTTPException) и превращал их в 500:

```python
# До исправления:
try:
    # ... validation code ...
    if file.content_type not in settings.allowed_file_types:
        raise HTTPException(status_code=400, detail=f"Тип файла {file.content_type} не разрешен")
    # ... upload code ...
except Exception as e:  # ❌ Ловит ВСЕ исключения, включая HTTPException!
    logger.error(f"Error uploading media file: {e}")
    raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")
```

---

## ✅ Решение

### Правильная обработка исключений

Добавлен проброс HTTPException **перед** обработкой общих исключений:

```python
# После исправления:
try:
    # ... validation code ...
    if file.content_type not in settings.allowed_file_types:
        raise HTTPException(status_code=400, detail=f"Тип файла {file.content_type} не разрешен")
    # ... upload code ...
except HTTPException:
    # ✅ Пробрасываем HTTPException с правильным status code
    raise
except Exception as e:
    logger.error(f"Error uploading media file: {e}")
    raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")
```

### Принцип работы

1. **Validation errors** → HTTP 400 (Bad Request)
2. **Not found errors** → HTTP 404 (Not Found)
3. **Business logic errors** → HTTP 422 (Unprocessable Entity)
4. **Unexpected errors** → HTTP 500 (Internal Server Error)

---

## 📊 Разрешённые типы файлов

### Images (Фото)
- ✅ `image/jpeg` - JPEG/JPG фотографии
- ✅ `image/png` - PNG изображения с прозрачностью
- ✅ `image/gif` - GIF анимация
- ✅ `image/webp` - WebP современный формат

### Videos (Видео)
- ✅ `video/mp4` - MP4 видео
- ✅ `video/quicktime` - MOV видео (QuickTime)

### ❌ НЕ разрешённые типы
- ❌ `image/svg+xml` - SVG векторная графика
- ❌ `application/pdf` - PDF документы
- ❌ `text/*` - Текстовые файлы
- ❌ Любые другие типы не из списка выше

---

## 🔄 Проверка исправления

### Тест 1: Загрузка JPG (должно работать ✅)
```bash
curl -X POST http://localhost:8004/api/v1/media/upload \
  -F "file=@test.jpg" \
  -F "request_number=TEST-001" \
  -F "category=request_photo"
```

**Ожидаемый результат**: `200 OK` с данными загруженного файла

### Тест 2: Загрузка SVG (должно вернуть 400 ✅)
```bash
curl -X POST http://localhost:8004/api/v1/media/upload \
  -F "file=@test.svg" \
  -F "request_number=TEST-001" \
  -F "category=request_photo"
```

**Ожидаемый результат**: `400 Bad Request`
```json
{
  "detail": "Тип файла image/svg+xml не разрешен"
}
```

### Тест 3: Неожиданная ошибка (должно вернуть 500)
Если произойдёт реальная ошибка (например, база данных недоступна):

**Ожидаемый результат**: `500 Internal Server Error`
```json
{
  "detail": "Ошибка при загрузке файла"
}
```

---

## 📝 Изменённые файлы

### `/app/api/v1/media.py`

**Строки**: 111-116

**Изменение**:
```diff
         return MediaUploadResponse(
             media_file=MediaFileResponse.model_validate(media_file),
             file_url=file_url,
             message="Файл успешно загружен"
         )

+    except HTTPException:
+        # Пробрасываем HTTPException с правильным status code
+        raise
     except Exception as e:
         logger.error(f"Error uploading media file: {e}")
         raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")
```

---

## 🎯 Рекомендации пользователю

### Для тестирования через HTML интерфейс:

1. **Используйте JPG или PNG файлы** для загрузки фотографий
2. **Используйте MP4 файлы** для загрузки видео
3. **Избегайте SVG, PDF и других форматов** - они вернут ошибку 400

### Если нужно добавить новые типы файлов:

Отредактируйте `app/core/config.py`:

```python
class Settings(BaseSettings):
    allowed_file_types: List[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        # Добавьте новые типы здесь:
        # "image/svg+xml",  # Если хотите разрешить SVG
        # "application/pdf",  # Если хотите разрешить PDF
    ]
```

---

## ✅ Статус

- [x] Проблема диагностирована
- [x] Исправление применено
- [x] Контейнер пересобран
- [x] Сервис запущен
- [x] Документация обновлена
- [ ] Тестирование пользователем (загрузка JPG файла)

**Статус**: ✅ **ИСПРАВЛЕНО** - Ожидает тестирования пользователем

---

## 📚 Связанные документы

- `ASYNC_MIGRATION_COMPLETED.md` - Миграция на Async SQLAlchemy
- `UPLOAD_FIX_APPLIED.md` - Исправление duplicate key error
- `ALL_FIXES_SUMMARY.md` - Сводка всех исправлений
- `FINAL_STATUS.md` - Финальный статус проекта


