"""
Сервис для поиска и фильтрации медиа-файлов
Реализация на основе спецификации photo.md
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models.media import MediaFile, MediaTag
from app.db.database import get_db_context

logger = logging.getLogger(__name__)


class MediaSearchService:
    """Сервис для поиска и фильтрации медиа-файлов"""

    async def search_media(
        self,
        query: Optional[str] = None,
        request_numbers: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        file_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        telegram_file_id: Optional[str] = None,
        uploaded_by: Optional[int] = None,
        status: str = "active",
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Универсальный поиск медиа-файлов с фильтрами
        """
        logger.info(f"Searching media with query: {query}, filters: tags={tags}, categories={categories}")

        with get_db_context() as db:
            # Базовый запрос
            query_obj = db.query(MediaFile).filter(MediaFile.status == status)

            # Фильтр по текстовому запросу
            if query:
                query_obj = query_obj.filter(
                    or_(
                        MediaFile.description.ilike(f"%{query}%"),
                        MediaFile.caption.ilike(f"%{query}%"),
                        MediaFile.title.ilike(f"%{query}%"),
                        MediaFile.original_filename.ilike(f"%{query}%")
                    )
                )

            # Фильтр по номерам заявок
            if request_numbers:
                query_obj = query_obj.filter(MediaFile.request_number.in_(request_numbers))

            # Фильтр по тегам
            if tags:
                for tag in tags:
                    query_obj = query_obj.filter(MediaFile.tags.contains([tag]))

            # Фильтр по дате
            if date_from:
                query_obj = query_obj.filter(MediaFile.uploaded_at >= date_from)

            if date_to:
                query_obj = query_obj.filter(MediaFile.uploaded_at <= date_to)

            # Фильтр по типам файлов
            if file_types:
                query_obj = query_obj.filter(MediaFile.file_type.in_(file_types))

            # Фильтр по категориям
            if categories:
                query_obj = query_obj.filter(MediaFile.category.in_(categories))

            # Фильтр по Telegram file_id
            if telegram_file_id:
                query_obj = query_obj.filter(MediaFile.telegram_file_id == telegram_file_id)

            # Фильтр по загрузившему пользователю
            if uploaded_by:
                query_obj = query_obj.filter(MediaFile.uploaded_by_user_id == uploaded_by)

            # Подсчет общего количества
            total_count = query_obj.count()

            # Получение результатов с пагинацией
            results_orm = query_obj.order_by(MediaFile.uploaded_at.desc()).offset(offset).limit(limit).all()

            # Преобразуем в словари, пока сессия активна
            results = []
            for media_file in results_orm:
                result_dict = {
                    "id": media_file.id,
                    "telegram_channel_id": media_file.telegram_channel_id,
                    "telegram_message_id": media_file.telegram_message_id,
                    "telegram_file_id": media_file.telegram_file_id,
                    "file_type": media_file.file_type,
                    "original_filename": media_file.original_filename,
                    "file_size": media_file.file_size,
                    "mime_type": media_file.mime_type,
                    "description": media_file.description,
                    "caption": media_file.caption,
                    "request_number": media_file.request_number,
                    "uploaded_by_user_id": media_file.uploaded_by_user_id,
                    "category": media_file.category,
                    "tags": media_file.tags,
                    "upload_source": media_file.upload_source,
                    "status": media_file.status,
                    "uploaded_at": media_file.uploaded_at,
                    "archived_at": media_file.archived_at,
                    "created_at": media_file.uploaded_at,  # Пока используем uploaded_at
                    "updated_at": media_file.updated_at or media_file.uploaded_at,
                }
                results.append(result_dict)

            logger.info(f"Found {len(results)} media files (total: {total_count})")

            return {
                "results": results,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count,
                "filters_applied": {
                    "query": query,
                    "request_numbers": request_numbers,
                    "tags": tags,
                    "date_range": [date_from, date_to] if date_from or date_to else None,
                    "file_types": file_types,
                    "categories": categories,
                    "telegram_file_id": telegram_file_id,
                    "uploaded_by": uploaded_by
                }
            }

    async def get_popular_tags(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Возвращает популярные теги
        """
        with get_db_context() as db:
            popular_tags = db.query(MediaTag).order_by(MediaTag.usage_count.desc()).limit(limit).all()

            result = []
            for tag in popular_tags:
                result.append({
                    "tag": tag.tag_name,
                    "count": tag.usage_count,
                    "category": tag.tag_category,
                    "color": tag.color,
                    "is_system": tag.is_system
                })

            logger.info(f"Retrieved {len(result)} popular tags")
            return result

    async def get_media_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику медиа-файлов
        """
        with get_db_context() as db:
            # Общая статистика
            total_files = db.query(MediaFile).filter(MediaFile.status == "active").count()
            total_size = db.query(func.sum(MediaFile.file_size)).filter(MediaFile.status == "active").scalar() or 0

            # Статистика по типам файлов
            file_types_stats = db.query(
                MediaFile.file_type,
                func.count(MediaFile.id).label('count'),
                func.sum(MediaFile.file_size).label('total_size')
            ).filter(MediaFile.status == "active").group_by(MediaFile.file_type).all()

            # Статистика по категориям
            categories_stats = db.query(
                MediaFile.category,
                func.count(MediaFile.id).label('count')
            ).filter(MediaFile.status == "active").group_by(MediaFile.category).all()

            # Статистика загрузок по дням (последние 30 дней)
            from datetime import timedelta
            date_30_days_ago = datetime.now() - timedelta(days=30)

            daily_uploads = db.query(
                func.date(MediaFile.uploaded_at).label('date'),
                func.count(MediaFile.id).label('count')
            ).filter(
                MediaFile.uploaded_at >= date_30_days_ago,
                MediaFile.status == "active"
            ).group_by(func.date(MediaFile.uploaded_at)).order_by(func.date(MediaFile.uploaded_at)).all()

            # Топ тегов
            top_tags = await self.get_popular_tags(limit=10)

            result = {
                "total_files": total_files,
                "total_size_bytes": int(total_size),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_types": [
                    {
                        "type": stat.file_type,
                        "count": stat.count,
                        "size_bytes": int(stat.total_size or 0),
                        "size_mb": round((stat.total_size or 0) / (1024 * 1024), 2)
                    }
                    for stat in file_types_stats
                ],
                "categories": [
                    {"category": stat.category, "count": stat.count}
                    for stat in categories_stats
                ],
                "daily_uploads": [
                    {"date": stat.date.isoformat(), "count": stat.count}
                    for stat in daily_uploads
                ],
                "top_tags": top_tags
            }

            logger.info(f"Generated media statistics: {total_files} files, {result['total_size_mb']} MB")
            return result

    async def find_similar_media(
        self,
        media_file_id: int,
        similarity_threshold: float = 0.7,
        limit: int = 10
    ) -> List[MediaFile]:
        """
        Поиск похожих медиа-файлов на основе тегов и метаданных
        """
        with get_db_context() as db:
            # Получаем исходный файл
            source_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
            if not source_file:
                logger.warning(f"Media file {media_file_id} not found")
                return []

            source_tags = set(source_file.tag_list)

            # Если нет тегов, ищем по категории
            if not source_tags:
                similar_files = db.query(MediaFile).filter(
                    MediaFile.category == source_file.category,
                    MediaFile.id != media_file_id,
                    MediaFile.status == "active"
                ).limit(limit).all()

                logger.info(f"Found {len(similar_files)} similar files by category")
                return similar_files

            # Ищем файлы с похожими тегами
            similar_files = []
            candidates = db.query(MediaFile).filter(
                MediaFile.id != media_file_id,
                MediaFile.status == "active"
            ).all()

            for candidate in candidates:
                candidate_tags = set(candidate.tag_list)
                if not candidate_tags:
                    continue

                # Вычисляем коэффициент Жаккара
                intersection = len(source_tags.intersection(candidate_tags))
                union = len(source_tags.union(candidate_tags))

                if union > 0:
                    similarity = intersection / union
                    if similarity >= similarity_threshold:
                        similar_files.append((candidate, similarity))

            # Сортируем по убыванию схожести
            similar_files.sort(key=lambda x: x[1], reverse=True)
            result = [file_data[0] for file_data in similar_files[:limit]]

            logger.info(f"Found {len(result)} similar files for media {media_file_id}")
            return result

    async def get_request_media_timeline(self, request_number: str) -> List[Dict[str, Any]]:
        """
        Возвращает временную линию медиа-файлов для заявки
        """
        with get_db_context() as db:
            media_files = db.query(MediaFile).filter(
                MediaFile.request_number == request_number,
                MediaFile.status == "active"
            ).order_by(MediaFile.uploaded_at.asc()).all()

            timeline = []
            for media_file in media_files:
                timeline.append({
                    "id": media_file.id,
                    "timestamp": media_file.uploaded_at.isoformat(),
                    "file_type": media_file.file_type,
                    "category": media_file.category,
                    "description": media_file.description,
                    "tags": media_file.tag_list,
                    "file_size": media_file.file_size,
                    "filename": media_file.original_filename
                })

            logger.info(f"Generated timeline for request {request_number}: {len(timeline)} files")
            return timeline

    async def search_by_date_range(
        self,
        date_from: datetime,
        date_to: datetime,
        group_by: str = "day",  # day, week, month
        categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Поиск медиа-файлов по диапазону дат с группировкой
        """
        with get_db_context() as db:
            query = db.query(MediaFile).filter(
                MediaFile.uploaded_at >= date_from,
                MediaFile.uploaded_at <= date_to,
                MediaFile.status == "active"
            )

            if categories:
                query = query.filter(MediaFile.category.in_(categories))

            # Группировка по периодам
            if group_by == "day":
                date_func = func.date(MediaFile.uploaded_at)
            elif group_by == "week":
                date_func = func.date_trunc('week', MediaFile.uploaded_at)
            elif group_by == "month":
                date_func = func.date_trunc('month', MediaFile.uploaded_at)
            else:
                date_func = func.date(MediaFile.uploaded_at)

            grouped_data = query.with_entities(
                date_func.label('period'),
                func.count(MediaFile.id).label('count'),
                func.sum(MediaFile.file_size).label('total_size')
            ).group_by(date_func).order_by(date_func).all()

            result = {
                "date_range": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat()
                },
                "group_by": group_by,
                "categories": categories,
                "data": [
                    {
                        "period": item.period.isoformat() if hasattr(item.period, 'isoformat') else str(item.period),
                        "count": item.count,
                        "size_bytes": int(item.total_size or 0),
                        "size_mb": round((item.total_size or 0) / (1024 * 1024), 2)
                    }
                    for item in grouped_data
                ],
                "total_files": sum(item.count for item in grouped_data),
                "total_size_mb": round(sum(item.total_size or 0 for item in grouped_data) / (1024 * 1024), 2)
            }

            logger.info(f"Date range search completed: {result['total_files']} files found")
            return result

    async def get_unused_tags(self, min_usage: int = 1) -> List[Dict[str, Any]]:
        """
        Возвращает неиспользуемые или малоиспользуемые теги
        """
        with get_db_context() as db:
            unused_tags = db.query(MediaTag).filter(
                MediaTag.usage_count < min_usage
            ).order_by(MediaTag.created_at.desc()).all()

            result = []
            for tag in unused_tags:
                result.append({
                    "tag": tag.tag_name,
                    "count": tag.usage_count,
                    "category": tag.tag_category,
                    "created_at": tag.created_at.isoformat(),
                    "is_system": tag.is_system
                })

            logger.info(f"Found {len(result)} unused/rarely used tags")
            return result
