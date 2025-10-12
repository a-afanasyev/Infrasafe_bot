# Техническое задание: Media Storage Service

## 1. Общее описание

### 1.1 Назначение
Media Storage Service - сервис для хранения, управления и доступа к медиафайлам (фото, видео, документы), связанным с заявками в системе управления.

### 1.2 Цели
- Централизованное хранение медиафайлов
- Эффективный поиск и фильтрация медиаконтента
- Управление метаданными и категоризация файлов
- Обнаружение и предотвращение дубликатов
- Интеграция с системой заявок и отчетов
- Обеспечение быстрого доступа к файлам

### 1.3 Ключевые характеристики
- **Порт**: 8004
- **Тип нагрузки**: Read-heavy (70% чтение, 30% запись)
- **Критичность**: Средняя
- **Масштабирование**: Горизонтальное

## 2. Функциональные требования

### 2.1 Модуль загрузки файлов

#### 2.1.1 Методы загрузки
- HTTP POST multipart/form-data
- Base64 encoded данные
- Загрузка по URL (внешние источники)
- Resumable upload для больших файлов
- Batch upload (множественная загрузка)
- Chunked upload с resume capability

#### 2.1.2 Валидация файлов
**Проверки при загрузке:**
- Размер файла (max 20MB для фото, 100MB для видео)
- MIME type validation
- Проверка расширения файла
- Сканирование на вирусы
- Content validation (corrupted files)
- Metadata extraction

**Разрешенные типы файлов:**
- Изображения: JPEG, PNG, GIF, WebP
- Видео: MP4, AVI, MOV, WebM
- Документы: PDF, DOC, DOCX, XLS, XLSX
- Аудио: MP3, WAV, OGG

#### 2.1.3 Обработка дубликатов
**Стратегии обнаружения:**
- Hash-based detection (SHA-256)
- Composite key: `{request_number}:{category}:{file_hash}`
- Perceptual hashing для изображений
- Binary comparison

**Политики обработки:**
- **STRICT** - отклонить загрузку дубликата
- **IGNORE** - вернуть существующий файл
- **REPLACE** - заменить старый файл новым
- **VERSION** - создать версию файла

#### 2.1.4 Metadata Extraction
Автоматическое извлечение:
- EXIF данные из фотографий
- Геолокация (если доступна)
- Дата и время съемки
- Параметры камеры
- Размеры изображения
- Длительность видео
- Битрейт и кодеки

#### 2.1.5 Upload Sessions
- Tracking прогресса загрузки
- Resume capability при сбоях
- Multi-part upload для больших файлов
- Временное хранилище для незавершенных загрузок
- Автоматическая очистка старых сессий

### 2.2 Модуль хранения

#### 2.2.1 Storage Backend (Q4.1)

**Принято решение**: Telegram Channels как основное хранилище

**Обоснование**:
- Неограниченное бесплатное хранилище
- Встроенное в Telegram Bot API
- Автоматическое сжатие и оптимизация
- CDN доставка по всему миру
- Не требует отдельной инфраструктуры

**Текущие лимиты** (согласованы):
- Max файлов на заявку: 5 файлов
- Max размер файла: 20 MB
- Поддерживаемые форматы: JPEG, PNG, MP4
- Max storage на пользователя: 1 GB
- Общий лимит организации: без ограничений (Telegram)

**Примечания**:
- PDF для документов - в будущем
- Видео до 50 MB - в будущем
- Batch upload 10 файлов - в будущем

**Альтернативные backend'ы** (для будущего):
- Local filesystem (для разработки)
- Cloud storage (S3, Google Cloud Storage, Azure Blob)
- CDN integration
- Hybrid approach (hot/cold storage)

#### 2.2.2 File Organization
**Структура хранения:**
```
/media/
  /{year}/
    /{month}/
      /{category}/
        /{file_hash}.{extension}
```

**Категории файлов:**
- `request_photo` - Фото заявок
- `request_video` - Видео заявок
- `report_before` - Фото "До работ"
- `report_after` - Фото "После работ"
- `report_process` - Фото процесса работ
- `document` - Документы
- `invoice` - Счета и накладные
- `other` - Прочее

#### 2.2.3 File Lifecycle
**Статусы файлов:**
- `active` - Активный файл
- `archived` - Архивированный
- `deleted` - Помечен на удаление
- `quarantine` - На карантине (проверка)

**Политики хранения:**
- Active files: горячее хранилище
- Archived files (>1 year): холодное хранилище
- Deleted files: retention 30 days, затем полное удаление
- Quarantine: автоматическое удаление через 7 days

#### 2.2.4 Metadata Storage
**База данных метаданных:**
- Связь файл ↔ заявка
- Информация о загрузке (кто, когда, откуда)
- Теги и категории
- Hash и размер файла
- Путь к файлу в storage
- Статус и история изменений

### 2.3 Модуль поиска и доступа

#### 2.3.1 Search Capabilities
**Полнотекстовый поиск:**
- По описанию файла
- По тегам
- По имени файла
- По caption/title

**Фильтрация:**
- По request_number
- По категории
- По дате загрузки
- По пользователю
- По типу файла
- По размеру
- По статусу

**Сортировка:**
- По дате (новые/старые)
- По размеру
- По релевантности
- По популярности

#### 2.3.2 Advanced Search
- Visual similarity search (похожие изображения)
- Поиск по содержимому (OCR для документов)
- Геолокационный поиск (в радиусе)
- Timeline view (хронология по заявке)
- Grouped search (группировка по заявкам)

#### 2.3.3 File Access
**Методы доступа:**
- Direct URL (с подписью)
- Временные ссылки (expiring URLs)
- Streaming для видео
- Thumbnails для изображений
- Download в различных форматах

**Контроль доступа:**
- Role-based access (RBAC)
- Per-file permissions
- Audit log всех обращений
- Rate limiting по IP

#### 2.3.4 Thumbnails & Previews
**Автоматическая генерация:**
- Thumbnails: 150x150, 300x300, 600x600
- Previews для документов (первая страница)
- Video thumbnails (первый кадр, timeline sprites)
- Оптимизация размера (WebP, compression)

### 2.4 Модуль тегирования

#### 2.4.1 Tag System
**Типы тегов:**
- **User tags** - созданные пользователями
- **System tags** - автоматические (category, request_number)
- **Auto tags** - из ML/AI (content analysis)
- **Location tags** - геолокация

**Tag Management:**
- Создание/удаление тегов
- Bulk tagging
- Tag suggestions (autocomplete)
- Popular tags
- Tag hierarchy (parent/child)

#### 2.4.2 Auto-Tagging
Автоматическое добавление тегов:
- По категории файла
- По request_number
- По типу файла
- По timestamp (год, месяц)
- По геолокации (если доступна)

### 2.5 Модуль аналитики

#### 2.5.1 Statistics
**Метрики:**
- Общее количество файлов
- Объем занятого пространства
- Файлы по категориям
- Файлы по типам
- Upload rate (файлов/день)
- Popular files (most accessed)

#### 2.5.2 Timeline & History
- История загрузок по заявке
- Chronological timeline
- Before/After comparisons
- Версионирование файлов
- Audit trail

#### 2.5.3 Reports
- Storage usage reports
- Upload/download statistics
- User activity reports
- File type distribution
- Growth trends

## 3. API Specifications

### 3.1 RESTful API

#### Upload Endpoints
```
POST   /api/v1/media/upload
POST   /api/v1/media/upload-report
POST   /api/v1/media/upload-batch
POST   /api/v1/media/upload-url
POST   /api/v1/media/resume/{session_id}
```

#### File Management Endpoints
```
GET    /api/v1/media/files
GET    /api/v1/media/files/{file_id}
PUT    /api/v1/media/files/{file_id}
DELETE /api/v1/media/files/{file_id}
POST   /api/v1/media/files/{file_id}/archive
POST   /api/v1/media/files/{file_id}/restore
GET    /api/v1/media/files/{file_id}/download
GET    /api/v1/media/files/{file_id}/thumbnail
```

#### Search Endpoints
```
POST   /api/v1/media/search
GET    /api/v1/media/search/advanced
POST   /api/v1/media/search/visual
GET    /api/v1/media/request/{request_number}
GET    /api/v1/media/timeline/{request_number}
```

#### Tag Endpoints
```
GET    /api/v1/media/tags
POST   /api/v1/media/tags
DELETE /api/v1/media/tags/{tag_id}
POST   /api/v1/media/files/{file_id}/tags
DELETE /api/v1/media/files/{file_id}/tags/{tag_id}
GET    /api/v1/media/tags/suggestions
```

#### Analytics Endpoints
```
GET    /api/v1/media/stats
GET    /api/v1/media/stats/category
GET    /api/v1/media/stats/timeline
GET    /api/v1/media/stats/storage
GET    /api/v1/media/reports/{type}
```

#### Duplicate Check Endpoints
```
POST   /api/v1/media/check-duplicate
GET    /api/v1/media/duplicates
POST   /api/v1/media/duplicates/merge
```

### 3.2 WebSocket API
```
/ws/media/upload/{session_id} - Upload progress tracking
/ws/media/processing - Real-time processing updates
```

## 4. Асинхронные задачи

### 4.1 Очереди и приоритеты

#### HIGH Priority (9-10)
- `media.upload.urgent` - Срочная загрузка (emergency requests)
- `media.virus.scan` - Сканирование на вирусы

#### MEDIUM Priority (4-8)
- `media.upload.process` - Обработка загруженных файлов
- `media.thumbnail.generate` - Генерация thumbnails
- `media.metadata.extract` - Извлечение метаданных
- `media.duplicate.check` - Проверка дубликатов

#### LOW Priority (1-3)
- `media.archive.cold` - Перенос в холодное хранилище
- `media.cleanup.deleted` - Очистка удаленных файлов
- `media.optimize.storage` - Оптимизация хранилища
- `media.stats.calculate` - Расчет статистики

### 4.2 Scheduled Tasks

#### Daily Tasks
- `media.cleanup.temp` - 02:00 - Очистка временных файлов
- `media.sessions.cleanup` - 03:00 - Очистка старых upload sessions
- `media.stats.daily` - 23:55 - Дневная статистика

#### Weekly Tasks
- `media.archive.old` - Sunday 01:00 - Архивация старых файлов
- `media.thumbnails.regenerate` - Sunday 02:00 - Регенерация thumbnails
- `media.orphans.detect` - Monday 03:00 - Поиск orphan files

#### Monthly Tasks
- `media.storage.optimize` - 1st, 00:00 - Оптимизация хранилища
- `media.duplicates.analyze` - 1st, 02:00 - Анализ дубликатов
- `media.reports.monthly` - 1st, 09:00 - Месячный отчет

## 5. События и интеграции

### 5.1 Публикуемые события
```
media.file.uploaded
media.file.updated
media.file.deleted
media.file.archived
media.file.scanned
media.thumbnail.generated
media.duplicate.detected
media.quota.warning
media.quota.exceeded
```

### 5.2 Подписки на события
```
core.request.created - Для связывания файлов с заявкой
core.request.completed - Для архивации медиа
core.request.cancelled - Для cleanup файлов
```

### 5.3 Webhooks
- Уведомления о завершении загрузки
- Уведомления об обработке файлов
- Алерты по квотам хранилища
- Результаты проверки дубликатов

## 6. Безопасность

### 6.1 Аутентификация и авторизация
- JWT токены для API
- Role-based access control
- Per-file permissions
- Signed URLs для прямого доступа
- Token expiration для temporary links

### 6.2 Защита файлов
- Encryption at rest
- Encryption in transit (TLS)
- Virus scanning при загрузке
- Content validation
- Watermarking (опционально)

### 6.3 Rate Limiting
- Upload: 100 файлов/час на пользователя
- Download: 1000 файлов/час
- Search: 100 запросов/минуту
- API calls: 1000 requests/минуту

### 6.4 Data Privacy (Q1.2)

**Политика хранения**:
- Хранение: в стране использования системы
- Трансграничная передача: запрещена
- Compliance: согласно локальному законодательству
- Геолокация серверов: страна работы системы

**Категории файлов**:

**Обычные медиафайлы** (фото заявок, отчеты):
- Хранение: бессрочно или до архивации заявки
- Удаление: при архивации заявки (>1 год)
- Доступ: согласно ролям пользователей

**Верификационные документы** (паспорта, селфи):
- Хранение: временное, только на время проверки
- Удаление: СРАЗУ после принятия решения (одобрено/отклонено)
- Шифрование: обязательное (encryption at rest)
- Доступ: только верификаторы
- Audit: полное логирование доступа

**Data retention**:
- Active files: hot storage (Telegram channels)
- Deleted files: 30 days retention, затем полное удаление
- Verification documents: 0 days retention (удаление сразу)

**Compliance**:
- GDPR compliance
- Right to deletion
- Data export capability
- Access audit logs
- PII protection

## 7. Производительность

### 7.1 Требования
- Upload speed: 10 MB/s minimum
- Download speed: 50 MB/s minimum
- Thumbnail generation: < 2s
- Search response: < 500ms
- Metadata extraction: < 1s

### 7.2 Оптимизации
- CDN для статических файлов
- Кеширование метаданных
- Lazy loading thumbnails
- Batch processing
- Compression (gzip, brotli)
- Image optimization (WebP, AVIF)

### 7.3 Кеширование
- File metadata: 10 min
- Thumbnails: 24 hours
- Search results: 2 min
- Statistics: 1 hour
- Tags list: 30 min

## 8. База данных

### 8.1 Схема данных

#### Media_Files Table
- id (UUID)
- request_number
- category
- file_type
- file_size
- mime_type
- original_filename
- storage_path
- file_hash (SHA-256)
- duplicate_check_hash
- uploaded_by_user_id
- uploaded_at
- status
- metadata (JSON)
- created_at
- updated_at
- deleted_at

#### Media_Tags Table
- id
- name
- type (user, system, auto)
- usage_count
- created_at

#### Media_File_Tags Table
- file_id
- tag_id
- added_at
- added_by

#### Media_Channels Table (для Telegram backend)
- id
- channel_id
- channel_name
- category
- max_files
- current_files
- created_at

#### Upload_Sessions Table
- id
- user_id
- status
- total_size
- uploaded_size
- file_count
- expires_at
- created_at
- updated_at

#### Media_Thumbnails Table
- id
- file_id
- size (small, medium, large)
- storage_path
- generated_at

### 8.2 Индексы
- media_files(request_number)
- media_files(category, status)
- media_files(uploaded_by_user_id, uploaded_at)
- media_files(file_hash)
- media_files(duplicate_check_hash)
- media_file_tags(file_id)
- media_tags(name)
- upload_sessions(user_id, status)

### 8.3 Миграции
- Версионирование схемы
- Zero-downtime migrations
- Data migrations для изменения структуры
- Rollback capability

## 9. Мониторинг и логирование

### 9.1 Метрики
- Upload rate (files/sec)
- Download rate (files/sec)
- Storage usage (GB)
- Cache hit rate
- Thumbnail generation time
- Duplicate detection rate
- Error rate
- API response times

### 9.2 Логирование
- Structured logging (JSON)
- All file operations logged
- Upload/download audit trail
- Errors and exceptions
- Performance metrics

### 9.3 Alerting
- Storage quota warnings (>80%)
- High error rate (>5%)
- Slow uploads/downloads
- Virus detection
- Duplicate flood detection
- Service unavailability

### 9.4 Health Checks
```
GET /health          - Basic health
GET /health/ready    - Readiness probe
GET /health/live     - Liveness probe
GET /health/storage  - Storage backend status
```

## 10. Тестирование

### 10.1 Unit Tests
- File validation logic
- Hash calculation
- Metadata extraction
- Duplicate detection algorithms
- Tag management

### 10.2 Integration Tests
- Upload workflows
- Search functionality
- Storage backend integration
- Database operations
- Event publishing

### 10.3 Performance Tests
- 1000 concurrent uploads
- Large file uploads (100MB+)
- Search with large datasets
- Thumbnail generation load
- Storage stress tests

### 10.4 Security Tests
- Upload malicious files
- SQL injection in search
- Path traversal attacks
- CSRF attacks
- Rate limiting bypass

## 11. Deployment

### 11.1 Конфигурация
- Environment variables для credentials
- Storage backend configuration
- Feature flags
- Resource limits (upload size, storage quota)
- Cache settings

### 11.2 Контейнеризация
- Multi-stage Docker builds
- Non-root user
- Health checks
- Resource limits (CPU, Memory)
- Volume mounts для storage

### 11.3 Зависимости
- PostgreSQL 15+
- Redis 7+ (кеширование)
- Storage backend (S3/GCS/Telegram)
- Message queue (RabbitMQ)
- CDN (опционально)

### 11.4 Масштабирование
- Horizontal scaling: 2-10 instances
- Read replicas для БД
- CDN для статики
- Sharding по категориям (опционально)
- Load balancing

## 12. Документация

### 12.1 API Documentation
- OpenAPI 3.0 specification
- Interactive documentation (Swagger/ReDoc)
- Code examples для всех endpoints
- Error codes reference
- Rate limits documentation

### 12.2 Developer Guide
- Storage backend setup
- Local development setup
- Configuration guide
- Testing guide
- Deployment guide

### 12.3 User Guide
- How to upload files
- Search best practices
- Tagging guidelines
- Storage quotas
- File lifecycle

## 13. Error Handling

### 13.1 Error Codes
```
MEDIA_001 - File validation failed
MEDIA_002 - File too large
MEDIA_003 - Invalid file type
MEDIA_004 - Storage upload failed
MEDIA_005 - Duplicate file detected
MEDIA_006 - Storage quota exceeded
MEDIA_007 - File not found
MEDIA_008 - Permission denied
MEDIA_009 - Virus detected
MEDIA_010 - Processing failed
```

### 13.2 Error Responses
Стандартный формат ответа:
```json
{
  "error": {
    "code": "MEDIA_001",
    "message": "File validation failed",
    "details": "File size exceeds 20MB limit",
    "timestamp": "2025-10-10T12:00:00Z"
  }
}
```

## 14. SLA

### 14.1 Availability
- Uptime: 99.5%
- Planned maintenance: < 8 hours/month
- Incident response: < 30 min

### 14.2 Performance
- Upload API: < 1s (metadata save)
- Search API: < 500ms
- Download: < 100ms (URL generation)
- Thumbnail generation: < 3s

### 14.3 Data
- RPO: 4 hours
- RTO: 8 hours
- Backup retention: 90 days
- File recovery: 30 days retention

## 15. Риски и ограничения

### 15.1 Технические риски
- Storage backend failure
- Quota exhaustion
- Slow upload speeds
- Database bottlenecks
- CDN failures

### 15.2 Митигация
- Multiple storage backends
- Automatic cleanup policies
- Compression и optimization
- Read replicas
- CDN fallback

### 15.3 Ограничения
- Max file size: 100MB
- Max batch upload: 50 files
- Max storage per organization: 1TB
- Max files per request: 1000
- Rate limits: 100 uploads/hour per user

## 16. Roadmap

### Phase 1 (MVP)
- Basic file upload/download
- Metadata storage
- Simple search
- Tag system
- Duplicate detection

### Phase 2
- Advanced search (visual similarity)
- Thumbnail optimization
- CDN integration
- Video streaming
- Batch operations

### Phase 3
- ML-based auto-tagging
- OCR для документов
- Video transcoding
- Advanced analytics
- Mobile app SDK

### Phase 4
- Distributed storage
- Edge caching
- Real-time collaboration
- Version control
- Advanced permissions
