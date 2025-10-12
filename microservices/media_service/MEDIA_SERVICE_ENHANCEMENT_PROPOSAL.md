# 📷 Media Service - Enhancement Proposal & Analysis

## 📅 Дата анализа: 6 октября 2025

---

## 🔍 Текущий анализ Media Service

### ✅ Сильные стороны

1. **Стабильная архитектура**:
   - Async SQLAlchemy с PostgreSQL
   - Redis кеширование
   - Telegram channels как бесплатное хранилище
   - RESTful API с comprehensive документацией

2. **Хорошая функциональность**:
   - 4 файла, 4.15MB общий размер
   - Система тегов с категориями
   - Поиск по множественным фильтрам
   - Health endpoints и мониторинг

3. **Production ready**:
   - Все критические баги исправлены
   - Error handling с правильными HTTP status codes
   - Docker deployment готов

### ⚠️ Текущие ограничения

1. **Обработка файлов**: Только базовое сохранение
2. **Компрессия**: Отключена (`enable_compression: false`)
3. **AI/ML**: Нет автоматической обработки изображений
4. **Аналитика**: Базовая статистика без глубокой аналитики
5. **UX**: Нет веб-интерфейса для пользователей

---

## 🚀 Предложения по доработке

### 🎯 Приоритет 1: Критические улучшения

#### 1.1 Автоматическая система сжатия изображений

**Проблема**: Большие фото занимают много места и медленно загружаются

**Решение**:
```python
# app/services/image_processor.py
from PIL import Image
import io
from typing import Tuple

class ImageProcessor:
    """Автоматическая обработка изображений"""
    
    def __init__(self):
        self.max_dimensions = (1920, 1080)  # HD качество
        self.quality = 85  # JPEG качество
        self.thumbnail_size = (300, 300)    # Превью
    
    async def process_image(self, file_data: bytes, 
                          filename: str) -> dict:
        """Обработать изображение: сжатие + превью"""
        
        # Определить тип обработки
        if self._is_large_image(file_data):
            return await self._compress_large_image(file_data, filename)
        else:
            return await self._create_thumbnail_only(file_data, filename)
    
    def _is_large_image(self, file_data: bytes) -> bool:
        """Проверить нужно ли сжатие"""
        with Image.open(io.BytesIO(file_data)) as img:
            width, height = img.size
            return (width > self.max_dimensions[0] or 
                   height > self.max_dimensions[1] or
                   len(file_data) > 5 * 1024 * 1024)  # 5MB
    
    async def _compress_large_image(self, file_data: bytes, 
                                  filename: str) -> dict:
        """Сжать большое изображение"""
        
        with Image.open(io.BytesIO(file_data)) as img:
            # Конвертировать в RGB если нужно
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Изменить размер если нужно
            img.thumbnail(self.max_dimensions, Image.Resampling.LANCZOS)
            
            # Сжать
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=self.quality, 
                    optimize=True)
            compressed_data = output.getvalue()
            
            # Создать превью
            thumbnail_data = await self._create_thumbnail(img)
            
            return {
                'original_size': len(file_data),
                'compressed_size': len(compressed_data),
                'compression_ratio': len(compressed_data) / len(file_data),
                'compressed_data': compressed_data,
                'thumbnail_data': thumbnail_data,
                'processed': True
            }
    
    async def _create_thumbnail(self, img: Image.Image) -> bytes:
        """Создать превью изображения"""
        thumbnail = img.copy()
        thumbnail.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
        
        output = io.BytesIO()
        thumbnail.save(output, format='JPEG', quality=80)
        return output.getvalue()
```

**Интеграция в upload endpoint**:
```python
# app/api/v1/media.py
@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    # ... остальные параметры
    enable_compression: bool = Form(default=True),  # Новый параметр
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    # ... существующая валидация
    
    # Обработка изображения
    if file.content_type.startswith('image/') and enable_compression:
        processor = ImageProcessor()
        processed = await processor.process_image(file_data, file.filename)
        
        if processed['processed']:
            # Использовать сжатое изображение
            file_data = processed['compressed_data']
            thumbnail_data = processed['thumbnail_data']
            
            # Сохранить метаданные о сжатии
            compression_info = {
                'original_size': processed['original_size'],
                'compressed_size': processed['compressed_size'],
                'compression_ratio': processed['compression_ratio']
            }
        else:
            # Создать только превью
            thumbnail_data = processed['thumbnail_data']
            compression_info = None
    
    # ... остальная логика upload
```

**Преимущества**:
- 📉 Уменьшение размера файлов на 60-80%
- ⚡ Быстрая загрузка превью
- 💾 Экономия места в Telegram channels
- 📱 Лучший UX на мобильных устройствах

---

#### 1.2 Система автоматического тегирования (AI)

**Проблема**: Пользователи не всегда добавляют теги, поиск затруднен

**Решение**:
```python
# app/services/ai_tagger.py
import asyncio
from typing import List, Dict
import httpx

class AITagger:
    """Автоматическое тегирование с помощью AI"""
    
    def __init__(self):
        self.ai_service_url = "http://ai-service:8005"
        self.tag_categories = {
            'damage': ['crack', 'broken', 'damage', 'wear'],
            'electrical': ['wire', 'cable', 'socket', 'electrical'],
            'plumbing': ['pipe', 'water', 'leak', 'plumbing'],
            'cleaning': ['dirty', 'clean', 'maintenance'],
            'safety': ['danger', 'warning', 'safety', 'hazard']
        }
    
    async def analyze_image(self, file_data: bytes, 
                          context: dict) -> List[str]:
        """Анализировать изображение и предложить теги"""
        
        try:
            # Отправить в AI Service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_service_url}/api/v1/vision/analyze",
                    files={"image": file_data},
                    data={
                        "request_number": context.get('request_number'),
                        "category": context.get('category'),
                        "description": context.get('description', '')
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return self._process_ai_tags(result)
                else:
                    return self._fallback_tagging(context)
                    
        except Exception as e:
            logger.warning(f"AI tagging failed: {e}")
            return self._fallback_tagging(context)
    
    def _process_ai_tags(self, ai_result: dict) -> List[str]:
        """Обработать результат AI анализа"""
        tags = []
        
        # Извлечь теги из AI результата
        if 'objects' in ai_result:
            for obj in ai_result['objects']:
                if obj['confidence'] > 0.7:  # Высокая уверенность
                    tags.append(obj['name'].lower())
        
        if 'scene' in ai_result:
            scene_tags = self._map_scene_to_tags(ai_result['scene'])
            tags.extend(scene_tags)
        
        return list(set(tags))  # Убрать дубликаты
    
    def _fallback_tagging(self, context: dict) -> List[str]:
        """Резервное тегирование на основе контекста"""
        tags = []
        
        # Теги на основе категории
        category = context.get('category', '')
        if 'electrical' in category.lower():
            tags.append('electrical')
        elif 'plumbing' in category.lower():
            tags.append('plumbing')
        
        # Теги на основе описания
        description = context.get('description', '').lower()
        for category, keywords in self.tag_categories.items():
            if any(keyword in description for keyword in keywords):
                tags.append(category)
        
        return tags

# Интеграция в MediaStorageService
class MediaStorageService:
    async def upload_request_media(self, ...):
        # ... существующая логика
        
        # Автоматическое тегирование
        if settings.enable_auto_tagging and file_type == "photo":
            ai_tagger = AITagger()
            auto_tags = await ai_tagger.analyze_image(
                file_data, 
                {
                    'request_number': request_number,
                    'category': category,
                    'description': description
                }
            )
            
            # Добавить к существующим тегам
            if auto_tags:
                tags_list.extend(auto_tags)
                logger.info(f"Auto-generated tags: {auto_tags}")
```

**Преимущества**:
- 🤖 Автоматическое распознавание объектов на фото
- 🏷️ Улучшенный поиск без ручного тегирования
- 📊 Аналитика по типам проблем
- ⚡ Быстрая категоризация заявок

---

### 🎯 Приоритет 2: Функциональные улучшения

#### 2.1 Веб-интерфейс для управления медиа

**Проблема**: Нет удобного UI для просмотра и управления файлами

**Решение**:
```html
<!-- app/static/media-dashboard.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Media Dashboard - UK Management</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">📷 Media Dashboard</h1>
        
        <!-- Статистика -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold">Всего файлов</h3>
                <p class="text-3xl font-bold text-blue-600" id="total-files">-</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold">Общий размер</h3>
                <p class="text-3xl font-bold text-green-600" id="total-size">-</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold">За сегодня</h3>
                <p class="text-3xl font-bold text-purple-600" id="today-uploads">-</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold">Популярные теги</h3>
                <p class="text-3xl font-bold text-orange-600" id="top-tags">-</p>
            </div>
        </div>
        
        <!-- Фильтры поиска -->
        <div class="bg-white p-6 rounded-lg shadow mb-8">
            <h2 class="text-xl font-semibold mb-4">🔍 Поиск медиа</h2>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <input type="text" id="search-query" placeholder="Поиск по тексту..." 
                       class="border rounded px-3 py-2">
                <select id="category-filter" class="border rounded px-3 py-2">
                    <option value="">Все категории</option>
                    <option value="request_photo">Фото заявок</option>
                    <option value="completion_photo">Фото завершения</option>
                </select>
                <input type="date" id="date-from" class="border rounded px-3 py-2">
                <input type="date" id="date-to" class="border rounded px-3 py-2">
                <button onclick="searchMedia()" 
                        class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                    Поиск
                </button>
            </div>
        </div>
        
        <!-- Галерея медиа -->
        <div class="bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-semibold mb-4">📸 Галерея</h2>
            <div id="media-gallery" class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
                <!-- Динамически загружаемые карточки -->
            </div>
        </div>
    </div>
    
    <script>
        // JavaScript для интерактивности
        async function loadStatistics() {
            const response = await fetch('/api/v1/media/statistics');
            const stats = await response.json();
            
            document.getElementById('total-files').textContent = stats.total_files;
            document.getElementById('total-size').textContent = stats.total_size_mb + ' MB';
            // ... остальная логика
        }
        
        async function searchMedia() {
            const query = document.getElementById('search-query').value;
            const category = document.getElementById('category-filter').value;
            const dateFrom = document.getElementById('date-from').value;
            const dateTo = document.getElementById('date-to').value;
            
            const params = new URLSearchParams();
            if (query) params.append('query', query);
            if (category) params.append('category', category);
            if (dateFrom) params.append('date_from', dateFrom);
            if (dateTo) params.append('date_to', dateTo);
            
            const response = await fetch(`/api/v1/media/search?${params}`);
            const results = await response.json();
            
            displayMediaGallery(results.results);
        }
        
        function displayMediaGallery(mediaFiles) {
            const gallery = document.getElementById('media-gallery');
            gallery.innerHTML = '';
            
            mediaFiles.forEach(file => {
                const card = createMediaCard(file);
                gallery.appendChild(card);
            });
        }
        
        function createMediaCard(file) {
            const card = document.createElement('div');
            card.className = 'bg-gray-50 p-4 rounded-lg border';
            
            card.innerHTML = `
                <img src="/api/v1/media/${file.id}/thumbnail" 
                     alt="${file.original_filename}"
                     class="w-full h-32 object-cover rounded mb-2">
                <h4 class="font-semibold truncate">${file.original_filename}</h4>
                <p class="text-sm text-gray-600">${file.category}</p>
                <p class="text-xs text-gray-500">${new Date(file.uploaded_at).toLocaleDateString()}</p>
                <div class="flex flex-wrap gap-1 mt-2">
                    ${file.tags.map(tag => `<span class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded">${tag}</span>`).join('')}
                </div>
            `;
            
            return card;
        }
        
        // Загрузить данные при загрузке страницы
        document.addEventListener('DOMContentLoaded', () => {
            loadStatistics();
            searchMedia();
        });
    </script>
</body>
</html>
```

**FastAPI интеграция**:
```python
# app/api/v1/dashboard.py
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/dashboard")
async def media_dashboard():
    """Веб-интерфейс для управления медиа"""
    return FileResponse("app/static/media-dashboard.html")

@router.get("/media/{media_id}/thumbnail")
async def get_media_thumbnail(media_id: int):
    """Получить превью изображения"""
    # Логика получения превью из Telegram или локального кеша
    pass
```

---

#### 2.2 Система дубликатов и дедупликации

**Проблема**: Пользователи могут загружать одинаковые файлы

**Решение**:
```python
# app/services/duplicate_detector.py
import hashlib
from typing import Optional, List

class DuplicateDetector:
    """Обнаружение и обработка дубликатов"""
    
    def __init__(self):
        self.similarity_threshold = 0.95  # 95% похожести
    
    async def check_duplicate(self, file_data: bytes, 
                            request_number: str = None) -> Optional[dict]:
        """Проверить является ли файл дубликатом"""
        
        # 1. Проверка по хешу файла
        file_hash = hashlib.md5(file_data).hexdigest()
        
        async with get_db_context() as db:
            # Поиск по хешу
            result = await db.execute(
                select(MediaFile).where(MediaFile.file_hash == file_hash)
            )
            exact_duplicate = result.scalar_one_or_none()
            
            if exact_duplicate:
                return {
                    'type': 'exact_duplicate',
                    'existing_file': exact_duplicate,
                    'confidence': 1.0,
                    'action': 'reuse'
                }
            
            # 2. Проверка визуального сходства для изображений
            if self._is_image(file_data):
                similar_files = await self._find_visual_similarities(
                    file_data, request_number, db
                )
                
                if similar_files:
                    return {
                        'type': 'visual_similar',
                        'existing_files': similar_files,
                        'confidence': max(f['similarity'] for f in similar_files),
                        'action': 'warn_or_reuse'
                    }
        
        return None
    
    async def _find_visual_similarities(self, file_data: bytes,
                                      request_number: str,
                                      db: AsyncSession) -> List[dict]:
        """Найти визуально похожие изображения"""
        
        # Получить изображения из той же заявки
        result = await db.execute(
            select(MediaFile).where(
                MediaFile.request_number == request_number,
                MediaFile.file_type == 'photo'
            )
        )
        existing_images = result.scalars().all()
        
        similar_files = []
        
        for existing_file in existing_images:
            # Скачать существующее изображение
            existing_data = await self._download_file(existing_file.telegram_file_id)
            
            # Вычислить сходство
            similarity = await self._calculate_image_similarity(
                file_data, existing_data
            )
            
            if similarity >= self.similarity_threshold:
                similar_files.append({
                    'file': existing_file,
                    'similarity': similarity
                })
        
        return sorted(similar_files, key=lambda x: x['similarity'], reverse=True)
    
    async def _calculate_image_similarity(self, img1_data: bytes, 
                                        img2_data: bytes) -> float:
        """Вычислить визуальное сходство изображений"""
        
        # Упрощенная версия - можно улучшить с помощью AI
        from PIL import Image
        import numpy as np
        
        img1 = Image.open(io.BytesIO(img1_data)).resize((64, 64))
        img2 = Image.open(io.BytesIO(img2_data)).resize((64, 64))
        
        # Преобразовать в numpy arrays
        arr1 = np.array(img1.convert('L'))  # Grayscale
        arr2 = np.array(img2.convert('L'))
        
        # Вычислить корреляцию
        correlation = np.corrcoef(arr1.flatten(), arr2.flatten())[0, 1]
        
        return correlation if not np.isnan(correlation) else 0.0

# Интеграция в upload
class MediaStorageService:
    async def upload_request_media(self, ...):
        # ... существующая валидация
        
        # Проверка дубликатов
        duplicate_detector = DuplicateDetector()
        duplicate_info = await duplicate_detector.check_duplicate(
            file_data, request_number
        )
        
        if duplicate_info:
            if duplicate_info['type'] == 'exact_duplicate':
                # Вернуть существующий файл
                return duplicate_info['existing_file']
            elif duplicate_info['type'] == 'visual_similar':
                # Предупредить пользователя
                logger.warning(f"Visual similarity detected: {duplicate_info['confidence']}")
                # Можно добавить параметр для принудительной загрузки
        
        # ... продолжение upload логики
```

---

### 🎯 Приоритет 3: Расширенные возможности

#### 3.1 Система аналитики и отчетов

**Проблема**: Нет глубокой аналитики использования медиа

**Решение**:
```python
# app/services/analytics_service.py
from typing import Dict, List
from datetime import datetime, timedelta

class MediaAnalyticsService:
    """Расширенная аналитика медиа"""
    
    async def generate_usage_report(self, 
                                  date_from: datetime,
                                  date_to: datetime) -> dict:
        """Генерация отчета об использовании"""
        
        async with get_db_context() as db:
            # Статистика загрузок по дням
            daily_uploads = await self._get_daily_uploads(db, date_from, date_to)
            
            # Топ пользователей
            top_users = await self._get_top_users(db, date_from, date_to)
            
            # Анализ типов файлов
            file_type_analysis = await self._analyze_file_types(db, date_from, date_to)
            
            # Тренды тегов
            tag_trends = await self._analyze_tag_trends(db, date_from, date_to)
            
            # Эффективность сжатия
            compression_stats = await self._get_compression_stats(db, date_from, date_to)
            
            return {
                'period': {
                    'from': date_from.isoformat(),
                    'to': date_to.isoformat(),
                    'days': (date_to - date_from).days
                },
                'daily_uploads': daily_uploads,
                'top_users': top_users,
                'file_types': file_type_analysis,
                'tag_trends': tag_trends,
                'compression': compression_stats,
                'generated_at': datetime.utcnow().isoformat()
            }
    
    async def _get_daily_uploads(self, db: AsyncSession, 
                               date_from: datetime,
                               date_to: datetime) -> List[dict]:
        """Статистика загрузок по дням"""
        
        result = await db.execute(
            select(
                func.date(MediaFile.uploaded_at).label('date'),
                func.count(MediaFile.id).label('count'),
                func.sum(MediaFile.file_size).label('total_size')
            ).where(
                MediaFile.uploaded_at >= date_from,
                MediaFile.uploaded_at <= date_to
            ).group_by(func.date(MediaFile.uploaded_at))
            .order_by('date')
        )
        
        return [
            {
                'date': row.date.isoformat(),
                'count': row.count,
                'total_size_mb': round(row.total_size / (1024*1024), 2)
            }
            for row in result
        ]
    
    async def _get_top_users(self, db: AsyncSession,
                           date_from: datetime,
                           date_to: datetime) -> List[dict]:
        """Топ пользователи по количеству загрузок"""
        
        result = await db.execute(
            select(
                MediaFile.uploaded_by_user_id,
                func.count(MediaFile.id).label('upload_count'),
                func.sum(MediaFile.file_size).label('total_size')
            ).where(
                MediaFile.uploaded_at >= date_from,
                MediaFile.uploaded_at <= date_to,
                MediaFile.uploaded_by_user_id.isnot(None)
            ).group_by(MediaFile.uploaded_by_user_id)
            .order_by(func.count(MediaFile.id).desc())
            .limit(10)
        )
        
        return [
            {
                'user_id': row.uploaded_by_user_id,
                'upload_count': row.upload_count,
                'total_size_mb': round(row.total_size / (1024*1024), 2)
            }
            for row in result
        ]
    
    async def _get_compression_stats(self, db: AsyncSession,
                                   date_from: datetime,
                                   date_to: datetime) -> dict:
        """Статистика сжатия файлов"""
        
        # Предполагаем что есть поле compression_ratio в MediaFile
        result = await db.execute(
            select(
                func.count(MediaFile.id).label('total_compressed'),
                func.avg(MediaFile.compression_ratio).label('avg_compression'),
                func.sum(MediaFile.original_size).label('total_original_size'),
                func.sum(MediaFile.file_size).label('total_compressed_size')
            ).where(
                MediaFile.uploaded_at >= date_from,
                MediaFile.uploaded_at <= date_to,
                MediaFile.compression_ratio.isnot(None)
            )
        )
        
        row = result.first()
        if row and row.total_compressed > 0:
            saved_bytes = row.total_original_size - row.total_compressed_size
            saved_percentage = (saved_bytes / row.total_original_size) * 100
            
            return {
                'compressed_files': row.total_compressed,
                'average_compression_ratio': round(row.avg_compression, 2),
                'total_saved_mb': round(saved_bytes / (1024*1024), 2),
                'saved_percentage': round(saved_percentage, 1)
            }
        
        return {'compressed_files': 0}

# API endpoints для аналитики
@router.get("/analytics/usage-report")
async def get_usage_report(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    analytics_service: MediaAnalyticsService = Depends(get_analytics_service)
):
    """Получить отчет об использовании медиа"""
    return await analytics_service.generate_usage_report(date_from, date_to)

@router.get("/analytics/trends")
async def get_media_trends(
    days: int = Query(default=30),
    analytics_service: MediaAnalyticsService = Depends(get_analytics_service)
):
    """Получить тренды использования"""
    date_from = datetime.utcnow() - timedelta(days=days)
    date_to = datetime.utcnow()
    
    return await analytics_service.generate_usage_report(date_from, date_to)
```

---

#### 3.2 Система уведомлений о медиа

**Проблема**: Нет уведомлений о новых медиа файлах

**Решение**:
```python
# app/services/media_notifications.py
from typing import List, Dict

class MediaNotificationService:
    """Система уведомлений о медиа"""
    
    def __init__(self):
        self.notification_service_url = "http://notification-service:8006"
    
    async def notify_media_uploaded(self, media_file: MediaFile):
        """Уведомить о загрузке нового медиа"""
        
        # Определить получателей
        recipients = await self._get_notification_recipients(media_file)
        
        if not recipients:
            return
        
        # Подготовить данные уведомления
        notification_data = {
            'recipients': recipients,
            'template': 'media_uploaded',
            'data': {
                'file_type': media_file.file_type,
                'file_name': media_file.original_filename,
                'request_number': media_file.request_number,
                'category': media_file.category,
                'uploaded_by': media_file.uploaded_by_user_id,
                'file_url': await self._get_file_url(media_file),
                'thumbnail_url': await self._get_thumbnail_url(media_file)
            },
            'priority': self._get_notification_priority(media_file)
        }
        
        # Отправить уведомление
        await self._send_notification(notification_data)
    
    async def _get_notification_recipients(self, media_file: MediaFile) -> List[str]:
        """Получить список получателей уведомлений"""
        
        recipients = []
        
        # 1. Участники заявки
        if media_file.request_number:
            request_recipients = await self._get_request_participants(
                media_file.request_number
            )
            recipients.extend(request_recipients)
        
        # 2. Менеджеры категории
        category_managers = await self._get_category_managers(
            media_file.category
        )
        recipients.extend(category_managers)
        
        # 3. Администраторы (для критических тегов)
        if self._has_critical_tags(media_file.tags):
            admin_recipients = await self._get_admin_users()
            recipients.extend(admin_recipients)
        
        return list(set(recipients))  # Убрать дубликаты
    
    def _get_notification_priority(self, media_file: MediaFile) -> str:
        """Определить приоритет уведомления"""
        
        # Критические теги
        critical_tags = ['emergency', 'urgent', 'safety', 'danger']
        
        if any(tag in media_file.tags for tag in critical_tags):
            return 'high'
        
        # Категории заявок - высокий приоритет
        if media_file.category in ['request_photo', 'request_video']:
            return 'medium'
        
        # Остальные - низкий приоритет
        return 'low'
    
    async def _send_notification(self, notification_data: dict):
        """Отправить уведомление через Notification Service"""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.notification_service_url}/api/v1/notifications",
                    json=notification_data,
                    headers={"Authorization": f"Bearer {settings.service_token}"}
                )
                
                if response.status_code == 200:
                    logger.info(f"Notification sent successfully: {notification_data['template']}")
                else:
                    logger.error(f"Failed to send notification: {response.text}")
                    
        except Exception as e:
            logger.error(f"Notification service error: {e}")

# Интеграция в MediaStorageService
class MediaStorageService:
    async def upload_request_media(self, ...):
        # ... существующая логика upload
        
        # Создать запись в БД
        media_file = await self._save_media_metadata(...)
        
        # Отправить уведомление
        notification_service = MediaNotificationService()
        await notification_service.notify_media_uploaded(media_file)
        
        return media_file
```

---

#### 3.3 Система резервного копирования

**Проблема**: Нет резервного копирования критических медиа

**Решение**:
```python
# app/services/backup_service.py
from typing import List
import asyncio
from datetime import datetime

class MediaBackupService:
    """Система резервного копирования медиа"""
    
    def __init__(self):
        self.backup_channels = {
            'primary': settings.channel_backup,
            'secondary': '-1002951349062'  # Дополнительный backup канал
        }
        self.backup_schedule = {
            'critical': 'immediate',    # Критические файлы - сразу
            'important': 'daily',       # Важные - ежедневно
            'normal': 'weekly'          # Обычные - еженедельно
        }
    
    async def backup_media_file(self, media_file: MediaFile, 
                              priority: str = 'normal') -> dict:
        """Создать резервную копию файла"""
        
        # Определить канал для backup
        backup_channel = self._select_backup_channel(priority)
        
        # Скачать оригинальный файл
        original_data = await self._download_from_telegram(
            media_file.telegram_file_id
        )
        
        # Загрузить в backup канал
        backup_result = await self._upload_to_backup_channel(
            backup_channel, original_data, media_file
        )
        
        # Обновить запись в БД
        await self._update_backup_info(media_file, backup_result)
        
        return {
            'original_file_id': media_file.id,
            'backup_file_id': backup_result['file_id'],
            'backup_channel': backup_channel,
            'backup_timestamp': datetime.utcnow().isoformat(),
            'priority': priority
        }
    
    async def scheduled_backup(self):
        """Планируемое резервное копирование"""
        
        async with get_db_context() as db:
            # Файлы для backup по приоритету
            critical_files = await self._get_files_for_backup(db, 'critical')
            important_files = await self._get_files_for_backup(db, 'important')
            normal_files = await self._get_files_for_backup(db, 'normal')
            
            # Backup критических файлов
            for file in critical_files:
                try:
                    await self.backup_media_file(file, 'critical')
                    await asyncio.sleep(1)  # Не перегружать Telegram API
                except Exception as e:
                    logger.error(f"Failed to backup critical file {file.id}: {e}")
            
            # Backup важных файлов (ежедневно)
            if datetime.utcnow().hour == 2:  # В 2 ночи
                for file in important_files:
                    try:
                        await self.backup_media_file(file, 'important')
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Failed to backup important file {file.id}: {e}")
            
            # Backup обычных файлов (еженедельно)
            if datetime.utcnow().weekday() == 0:  # Понедельник
                for file in normal_files:
                    try:
                        await self.backup_media_file(file, 'normal')
                        await asyncio.sleep(3)
                    except Exception as e:
                        logger.error(f"Failed to backup normal file {file.id}: {e}")
    
    def _select_backup_channel(self, priority: str) -> str:
        """Выбрать канал для backup"""
        
        if priority == 'critical':
            return self.backup_channels['primary']
        else:
            # Ротация каналов для балансировки нагрузки
            return self.backup_channels['secondary']
    
    async def _get_files_for_backup(self, db: AsyncSession, 
                                  priority: str) -> List[MediaFile]:
        """Получить файлы для backup по приоритету"""
        
        if priority == 'critical':
            # Файлы с критическими тегами без backup
            result = await db.execute(
                select(MediaFile).where(
                    MediaFile.tags.contains(['emergency', 'urgent', 'safety']),
                    MediaFile.backup_file_id.is_(None)
                )
            )
        elif priority == 'important':
            # Файлы заявок без backup
            result = await db.execute(
                select(MediaFile).where(
                    MediaFile.category.in_(['request_photo', 'request_video']),
                    MediaFile.backup_file_id.is_(None),
                    MediaFile.uploaded_at >= datetime.utcnow() - timedelta(days=7)
                )
            )
        else:
            # Остальные файлы без backup
            result = await db.execute(
                select(MediaFile).where(
                    MediaFile.backup_file_id.is_(None),
                    MediaFile.uploaded_at >= datetime.utcnow() - timedelta(days=30)
                ).limit(100)  # Ограничить количество
            )
        
        return result.scalars().all()

# Scheduled task
@router.post("/internal/backup")
async def trigger_backup():
    """Запустить резервное копирование (internal endpoint)"""
    
    backup_service = MediaBackupService()
    await backup_service.scheduled_backup()
    
    return {"status": "backup_completed", "timestamp": datetime.utcnow().isoformat()}
```

---

## 📊 План внедрения

### 🎯 Фаза 1: Критические улучшения (2-3 недели)

1. **Автоматическое сжатие изображений**
   - [ ] Реализовать `ImageProcessor`
   - [ ] Интегрировать в upload endpoint
   - [ ] Добавить параметр `enable_compression`
   - [ ] Тестирование производительности

2. **AI автоматическое тегирование**
   - [ ] Интегрировать с AI Service
   - [ ] Реализовать fallback тегирование
   - [ ] Добавить confidence scoring
   - [ ] Настроить автоматическое применение тегов

### 🎯 Фаза 2: Функциональные улучшения (3-4 недели)

3. **Веб-интерфейс**
   - [ ] Создать media dashboard
   - [ ] Реализовать галерею с фильтрами
   - [ ] Добавить статистику в реальном времени
   - [ ] Интегрировать с существующим API

4. **Система дубликатов**
   - [ ] Реализовать hash-based detection
   - [ ] Добавить visual similarity для изображений
   - [ ] Интегрировать в upload flow
   - [ ] Добавить UI для управления дубликатами

### 🎯 Фаза 3: Расширенные возможности (4-5 недель)

5. **Расширенная аналитика**
   - [ ] Реализовать `MediaAnalyticsService`
   - [ ] Создать API endpoints для отчетов
   - [ ] Добавить визуализацию трендов
   - [ ] Интегрировать с dashboard

6. **Система уведомлений**
   - [ ] Реализовать `MediaNotificationService`
   - [ ] Интегрировать с Notification Service
   - [ ] Добавить priority-based уведомления
   - [ ] Настроить templates уведомлений

7. **Резервное копирование**
   - [ ] Реализовать `MediaBackupService`
   - [ ] Настроить scheduled tasks
   - [ ] Добавить priority-based backup
   - [ ] Создать monitoring backup процесса

---

## 💰 Оценка ресурсов

### 👥 Команда разработки

- **Backend Developer** (1.0 FTE) - 10 недель
- **Frontend Developer** (0.5 FTE) - 4 недели  
- **DevOps Engineer** (0.3 FTE) - 3 недели
- **QA Engineer** (0.5 FTE) - 5 недель

### 🛠️ Технические требования

1. **Дополнительные зависимости**:
   ```python
   # requirements.txt additions
   Pillow>=10.0.0          # Image processing
   opencv-python>=4.8.0    # Computer vision (для similarity)
   scikit-image>=0.21.0    # Image analysis
   numpy>=1.24.0           # Numerical operations
   apscheduler>=3.10.0     # Scheduled tasks
   ```

2. **Инфраструктура**:
   - Дополнительные Telegram channels для backup
   - Redis для кеширования processed images
   - Cron jobs для scheduled backup
   - Monitoring для новых метрик

3. **Storage**:
   - Локальный кеш для thumbnails (до 1GB)
   - Backup channels (до 50GB дополнительно)

---

## 📈 Ожидаемые результаты

### 🎯 Ключевые метрики

1. **Производительность**:
   - 📉 Уменьшение размера файлов на 60-80%
   - ⚡ Ускорение загрузки превью в 3-5 раз
   - 💾 Экономия storage на 40-60%

2. **Пользовательский опыт**:
   - 🎯 Автоматическое тегирование 90%+ файлов
   - 🔍 Улучшение поиска на 70%
   - 📱 Удобный веб-интерфейс
   - 🔔 Своевременные уведомления

3. **Надежность**:
   - 💾 100% backup coverage для критических файлов
   - 🛡️ Защита от дубликатов
   - 📊 Comprehensive мониторинг
   - 🔄 Автоматическое восстановление

### 📊 Business Impact

- **Экономия времени**: 2-3 часа в день на управление медиа
- **Улучшение качества**: Автоматическое тегирование и поиск
- **Снижение рисков**: Резервное копирование и мониторинг
- **Масштабируемость**: Готовность к росту объема медиа

---

## 🚀 Заключение

Media Service имеет отличную основу и готов к значительным улучшениям. Предложенные доработки превратят его в современную, эффективную систему управления медиа с AI-возможностями, автоматизацией и comprehensive аналитикой.

**Приоритет реализации**: Начать с автоматического сжатия изображений и AI тегирования, так как они дадут максимальный эффект при минимальных затратах.

**Следующий шаг**: Создать детальный технический план для Фазы 1 с конкретными задачами и сроками.

---

*Документ подготовлен: 6 октября 2025*  
*Статус: Готов к review и утверждению*

