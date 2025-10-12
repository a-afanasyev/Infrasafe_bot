"""
Сервис для проверки и управления дубликатами файлов
"""

import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.media import MediaFile
from app.db.database import get_db_context, get_db_context_sync

logger = logging.getLogger(__name__)


class DuplicatePolicy(Enum):
    """Политики обработки дубликатов файлов"""
    STRICT = "strict"      # Полностью запретить дубликаты
    WARNING = "warning"    # Разрешить с предупреждением
    REPLACE = "replace"    # Заменить существующий файл
    IGNORE = "ignore"      # Игнорировать дубликаты без ошибки


@dataclass
class DuplicateCheckResult:
    """Результат проверки дубликатов"""
    is_duplicate: bool
    existing_file: Optional[MediaFile] = None
    policy_applied: Optional[DuplicatePolicy] = None
    message: Optional[str] = None
    action_taken: Optional[str] = None


@dataclass
class DuplicateCheckRequest:
    """Запрос на проверку дубликатов"""
    request_number: str
    category: str
    file_data: bytes
    policy: DuplicatePolicy = DuplicatePolicy.STRICT


class DuplicateCheckerService:
    """Сервис для проверки и управления дубликатами файлов"""

    def __init__(self, default_policy: DuplicatePolicy = DuplicatePolicy.STRICT):
        self.default_policy = default_policy

    async def check_duplicate(
        self, 
        request_number: str, 
        category: str, 
        file_data: bytes,
        policy: Optional[DuplicatePolicy] = None
    ) -> DuplicateCheckResult:
        """
        Проверяет существование дубликата файла
        
        Args:
            request_number: Номер заявки
            category: Категория файла
            file_data: Содержимое файла в байтах
            policy: Политика обработки дубликатов
            
        Returns:
            DuplicateCheckResult с результатом проверки
        """
        if policy is None:
            policy = self.default_policy

        try:
            # Вычисляем хеш файла
            file_hash = MediaFile.calculate_file_hash(file_data)
            
            # Создаем ключ для проверки дубликатов
            duplicate_key = MediaFile.create_duplicate_key(request_number, category, file_hash)
            
            logger.info(f"Checking duplicate for request={request_number}, category={category}, hash={file_hash[:8]}...")

            # Проверяем существование дубликата в БД
            async with get_db_context() as db:
                existing_file = await self._find_existing_file(db, request_number, category, file_hash)
                
                if existing_file:
                    logger.warning(f"Duplicate file found: id={existing_file.id}, request={request_number}, category={category}")
                    return await self._handle_duplicate(existing_file, policy, duplicate_key)
                else:
                    logger.info(f"No duplicate found for request={request_number}, category={category}")
                    return DuplicateCheckResult(
                        is_duplicate=False,
                        message="File is unique, no duplicates found"
                    )

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return DuplicateCheckResult(
                is_duplicate=False,
                message=f"Error during duplicate check: {str(e)}"
            )

    async def _find_existing_file(
        self, 
        db: AsyncSession, 
        request_number: str, 
        category: str, 
        file_hash: str
    ) -> Optional[MediaFile]:
        """Находит существующий файл с таким же хешем"""
        try:
            result = await db.execute(
                select(MediaFile).where(
                    and_(
                        MediaFile.request_number == request_number,
                        MediaFile.category == category,
                        MediaFile.file_hash == file_hash,
                        MediaFile.status == "active"
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding existing file: {e}")
            return None

    async def _handle_duplicate(
        self, 
        existing_file: MediaFile, 
        policy: DuplicatePolicy,
        duplicate_key: str
    ) -> DuplicateCheckResult:
        """Обрабатывает найденный дубликат согласно политике"""
        
        if policy == DuplicatePolicy.STRICT:
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_file=existing_file,
                policy_applied=policy,
                message=f"Duplicate file detected. File already exists for request {existing_file.request_number}",
                action_taken="rejected"
            )
        
        elif policy == DuplicatePolicy.WARNING:
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_file=existing_file,
                policy_applied=policy,
                message=f"Warning: Duplicate file detected, but upload will proceed. Existing file ID: {existing_file.id}",
                action_taken="warning"
            )
        
        elif policy == DuplicatePolicy.REPLACE:
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_file=existing_file,
                policy_applied=policy,
                message=f"Duplicate file detected. Existing file will be replaced. Old file ID: {existing_file.id}",
                action_taken="replace"
            )
        
        elif policy == DuplicatePolicy.IGNORE:
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_file=existing_file,
                policy_applied=policy,
                message=f"Duplicate file detected, but upload will be ignored. Existing file ID: {existing_file.id}",
                action_taken="ignore"
            )
        
        else:
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_file=existing_file,
                policy_applied=policy,
                message=f"Unknown policy: {policy}",
                action_taken="rejected"
            )

    async def register_file(
        self, 
        media_file: MediaFile, 
        file_data: bytes
    ) -> None:
        """
        Регистрирует новый файл для проверки дубликатов
        
        Args:
            media_file: Объект MediaFile
            file_data: Содержимое файла в байтах
        """
        try:
            # Вычисляем хеш файла
            file_hash = MediaFile.calculate_file_hash(file_data)
            
            # Создаем ключ для проверки дубликатов
            duplicate_key = MediaFile.create_duplicate_key(
                media_file.request_number, 
                media_file.category, 
                file_hash
            )
            
            # Сохраняем хеши в объект
            media_file.file_hash = file_hash
            media_file.duplicate_check_hash = duplicate_key
            
            logger.info(f"File registered for duplicate checking: id={media_file.id}, hash={file_hash[:8]}...")
            
        except Exception as e:
            logger.error(f"Error registering file for duplicate check: {e}")

    async def get_duplicate_stats(self) -> Dict[str, Any]:
        """Возвращает статистику по дубликатам"""
        try:
            async with get_db_context() as db:
                # Подсчитываем общее количество файлов
                total_files = await db.execute(
                    select(MediaFile).where(MediaFile.status == "active")
                )
                total_count = len(total_files.scalars().all())
                
                # Подсчитываем уникальные хеши
                unique_hashes = await db.execute(
                    select(MediaFile.file_hash).where(
                        and_(
                            MediaFile.status == "active",
                            MediaFile.file_hash.isnot(None)
                        )
                    )
                )
                unique_hash_count = len(set(h[0] for h in unique_hashes.scalars().all() if h[0]))
                
                # Подсчитываем потенциальные дубликаты
                potential_duplicates = total_count - unique_hash_count
                
                return {
                    "total_files": total_count,
                    "unique_files": unique_hash_count,
                    "potential_duplicates": potential_duplicates,
                    "duplicate_percentage": round((potential_duplicates / total_count * 100), 2) if total_count > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"Error getting duplicate stats: {e}")
            return {
                "total_files": 0,
                "unique_files": 0,
                "potential_duplicates": 0,
                "duplicate_percentage": 0
            }

    async def cleanup_duplicates(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Очищает дубликаты файлов
        
        Args:
            dry_run: Если True, только показывает что будет удалено
            
        Returns:
            Словарь с результатами очистки
        """
        try:
            async with get_db_context() as db:
                # Находим файлы с одинаковыми хешами
                duplicate_groups = await self._find_duplicate_groups(db)
                
                cleanup_stats = {
                    "groups_found": len(duplicate_groups),
                    "files_to_remove": 0,
                    "space_saved_bytes": 0,
                    "dry_run": dry_run
                }
                
                if not dry_run:
                    # Реально удаляем дубликаты (оставляем самый старый файл в группе)
                    for group in duplicate_groups:
                        # Сортируем по дате загрузки, оставляем самый старый
                        group.sort(key=lambda x: x.uploaded_at)
                        files_to_remove = group[1:]  # Все кроме первого
                        
                        for file_to_remove in files_to_remove:
                            file_to_remove.status = "deleted"
                            cleanup_stats["files_to_remove"] += 1
                            cleanup_stats["space_saved_bytes"] += file_to_remove.file_size or 0
                    
                    await db.commit()
                    logger.info(f"Cleanup completed: {cleanup_stats['files_to_remove']} files removed")
                else:
                    # Подсчитываем для dry run
                    for group in duplicate_groups:
                        files_to_remove = group[1:]  # Все кроме первого
                        cleanup_stats["files_to_remove"] += len(files_to_remove)
                        cleanup_stats["space_saved_bytes"] += sum(f.file_size or 0 for f in files_to_remove)
                    
                    logger.info(f"Dry run completed: {cleanup_stats['files_to_remove']} files would be removed")
                
                return cleanup_stats
                
        except Exception as e:
            logger.error(f"Error cleaning up duplicates: {e}")
            return {
                "groups_found": 0,
                "files_to_remove": 0,
                "space_saved_bytes": 0,
                "dry_run": dry_run,
                "error": str(e)
            }

    async def _find_duplicate_groups(self, db: AsyncSession) -> List[List[MediaFile]]:
        """Находит группы файлов с одинаковыми хешами"""
        try:
            # Получаем все активные файлы с хешами
            result = await db.execute(
                select(MediaFile).where(
                    and_(
                        MediaFile.status == "active",
                        MediaFile.file_hash.isnot(None)
                    )
                )
            )
            all_files = result.scalars().all()
            
            # Группируем по хешам
            hash_groups = {}
            for file in all_files:
                if file.file_hash not in hash_groups:
                    hash_groups[file.file_hash] = []
                hash_groups[file.file_hash].append(file)
            
            # Возвращаем только группы с более чем одним файлом
            duplicate_groups = [group for group in hash_groups.values() if len(group) > 1]
            
            return duplicate_groups
            
        except Exception as e:
            logger.error(f"Error finding duplicate groups: {e}")
            return []
