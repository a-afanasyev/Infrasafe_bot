"""
Enhanced Streaming Upload Service for Media Service
Handles large file uploads without exhausting RAM through chunked processing
"""

import asyncio
import hashlib
import logging
import tempfile
import os
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional, Dict, Any, BinaryIO
from pathlib import Path

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.media import MediaFile, MediaUploadSession, MediaChannel
from app.services.telegram_client import TelegramClientService
from app.db.async_database import get_async_db_context
from app.core.config import settings, FileCategories, ErrorMessages

logger = logging.getLogger(__name__)

class StreamingUploadService:
    """Enhanced service for streaming large file uploads"""

    # Chunk size for streaming - 1MB chunks
    CHUNK_SIZE = 1024 * 1024  # 1MB
    # Maximum file size for streaming mode
    MAX_STREAMING_SIZE = 50 * 1024 * 1024  # 50MB
    # Minimum file size to trigger streaming mode
    MIN_STREAMING_SIZE = 5 * 1024 * 1024   # 5MB

    def __init__(self):
        self.telegram = TelegramClientService()
        self.temp_dir = Path(tempfile.gettempdir()) / "media_uploads"
        self.temp_dir.mkdir(exist_ok=True)

    async def should_use_streaming(self, file_size: int) -> bool:
        """Determine if file should use streaming upload"""
        return self.MIN_STREAMING_SIZE <= file_size <= self.MAX_STREAMING_SIZE

    async def create_upload_session(
        self,
        filename: str,
        file_size: int,
        content_type: str,
        request_number: str,
        category: str = FileCategories.REQUEST_PHOTO,
        uploaded_by: Optional[int] = None
    ) -> str:
        """Create an upload session for chunked uploads"""

        # Validate file size
        if file_size > self.MAX_STREAMING_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {self.MAX_STREAMING_SIZE // (1024*1024)}MB"
            )

        # Validate content type
        if content_type not in settings.allowed_file_types:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed: {content_type}"
            )

        session_id = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(filename + str(file_size))}"

        async with get_async_db_context() as db:
            upload_session = MediaUploadSession(
                session_id=session_id,
                original_filename=filename,
                file_size=file_size,
                content_type=content_type,
                request_number=request_number,
                category=category,
                uploaded_by_user_id=uploaded_by or 0,
                chunks_received=0,
                total_chunks=self._calculate_total_chunks(file_size),
                status="active"
            )

            db.add(upload_session)
            await db.commit()

        logger.info(f"Created upload session {session_id} for file {filename} ({file_size} bytes)")
        return session_id

    async def upload_chunk(
        self,
        session_id: str,
        chunk_index: int,
        chunk_data: bytes
    ) -> Dict[str, Any]:
        """Upload a single chunk of the file"""

        async with get_async_db_context() as db:
            # Get upload session
            result = await db.execute(
                select(MediaUploadSession).where(MediaUploadSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                raise HTTPException(status_code=404, detail="Upload session not found")

            if session.status != "active":
                raise HTTPException(status_code=400, detail="Upload session is not active")

            # Validate chunk index
            if chunk_index >= session.total_chunks:
                raise HTTPException(status_code=400, detail="Invalid chunk index")

            # Save chunk to temporary file
            chunk_file = self.temp_dir / f"{session_id}_chunk_{chunk_index}"

            try:
                with open(chunk_file, 'wb') as f:
                    f.write(chunk_data)

                # Update session
                session.chunks_received += 1
                session.bytes_received = session.bytes_received or 0
                session.bytes_received += len(chunk_data)
                session.updated_at = datetime.now(timezone.utc)

                await db.commit()

                progress = (session.chunks_received / session.total_chunks) * 100

                logger.debug(f"Chunk {chunk_index} uploaded for session {session_id}. Progress: {progress:.1f}%")

                return {
                    "chunk_index": chunk_index,
                    "chunks_received": session.chunks_received,
                    "total_chunks": session.total_chunks,
                    "progress": progress,
                    "complete": session.chunks_received >= session.total_chunks
                }

            except Exception as e:
                logger.error(f"Failed to save chunk {chunk_index} for session {session_id}: {e}")
                # Clean up failed chunk
                if chunk_file.exists():
                    chunk_file.unlink()
                raise HTTPException(status_code=500, detail="Failed to save chunk")

    async def finalize_upload(
        self,
        session_id: str,
        description: Optional[str] = None,
        tags: Optional[list] = None
    ) -> MediaFile:
        """Finalize the upload by assembling chunks and uploading to Telegram"""

        async with get_async_db_context() as db:
            # Get upload session
            result = await db.execute(
                select(MediaUploadSession).where(MediaUploadSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                raise HTTPException(status_code=404, detail="Upload session not found")

            if session.chunks_received < session.total_chunks:
                raise HTTPException(
                    status_code=400,
                    detail=f"Upload incomplete. {session.chunks_received}/{session.total_chunks} chunks received"
                )

            try:
                # Assemble file from chunks
                assembled_file = await self._assemble_chunks(session)

                # Upload to Telegram
                from app.services.media_storage import MediaStorageService
                storage_service = MediaStorageService()

                # Read assembled file
                with open(assembled_file, 'rb') as f:
                    file_data = f.read()

                # Upload using existing media storage service
                media_file = await storage_service.upload_request_media(
                    request_number=session.request_number,
                    file_data=file_data,
                    filename=session.original_filename,
                    content_type=session.content_type,
                    category=session.category,
                    description=description,
                    tags=tags,
                    uploaded_by=session.uploaded_by_user_id
                )

                # Update session status
                session.status = "completed"
                session.media_file_id = media_file.id
                session.completed_at = datetime.now(timezone.utc)

                await db.commit()

                # Cleanup temporary files
                await self._cleanup_session_files(session_id)

                logger.info(f"Finalized upload session {session_id}, created media file {media_file.id}")
                return media_file

            except Exception as e:
                # Mark session as failed
                session.status = "failed"
                session.error_message = str(e)
                await db.commit()

                # Cleanup temporary files
                await self._cleanup_session_files(session_id)

                logger.error(f"Failed to finalize upload session {session_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Upload finalization failed: {str(e)}")

    async def cancel_upload(self, session_id: str) -> bool:
        """Cancel an upload session"""

        async with get_async_db_context() as db:
            result = await db.execute(
                select(MediaUploadSession).where(MediaUploadSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return False

            session.status = "cancelled"
            session.cancelled_at = datetime.now(timezone.utc)
            await db.commit()

            # Cleanup temporary files
            await self._cleanup_session_files(session_id)

            logger.info(f"Cancelled upload session {session_id}")
            return True

    async def get_upload_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an upload session"""

        async with get_async_db_context() as db:
            result = await db.execute(
                select(MediaUploadSession).where(MediaUploadSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            progress = (session.chunks_received / session.total_chunks) * 100 if session.total_chunks > 0 else 0

            return {
                "session_id": session_id,
                "filename": session.original_filename,
                "file_size": session.file_size,
                "chunks_received": session.chunks_received,
                "total_chunks": session.total_chunks,
                "progress": progress,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                "media_file_id": session.media_file_id
            }

    async def stream_upload_directly(
        self,
        file: UploadFile,
        request_number: str,
        category: str = FileCategories.REQUEST_PHOTO,
        description: Optional[str] = None,
        tags: Optional[list] = None,
        uploaded_by: Optional[int] = None
    ) -> MediaFile:
        """Stream upload large file directly without chunking (for FastAPI UploadFile)"""

        # Validate file size by reading in chunks
        file_size = 0
        chunk_hasher = hashlib.sha256()
        temp_file = self.temp_dir / f"direct_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

        try:
            with open(temp_file, 'wb') as temp_f:
                while chunk := await file.read(self.CHUNK_SIZE):
                    file_size += len(chunk)

                    # Check size limit
                    if file_size > self.MAX_STREAMING_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large. Maximum size: {self.MAX_STREAMING_SIZE // (1024*1024)}MB"
                        )

                    chunk_hasher.update(chunk)
                    temp_f.write(chunk)

            # Validate content type
            if file.content_type not in settings.allowed_file_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {file.content_type}"
                )

            # Upload using media storage service
            from app.services.media_storage import MediaStorageService
            storage_service = MediaStorageService()

            with open(temp_file, 'rb') as f:
                file_data = f.read()

            media_file = await storage_service.upload_request_media(
                request_number=request_number,
                file_data=file_data,
                filename=file.filename,
                content_type=file.content_type,
                category=category,
                description=description,
                tags=tags,
                uploaded_by=uploaded_by
            )

            # Add file hash for integrity checking
            media_file.file_hash = chunk_hasher.hexdigest()

            logger.info(f"Streamed upload completed for {file.filename}, created media file {media_file.id}")
            return media_file

        finally:
            # Cleanup temporary file
            if temp_file.exists():
                temp_file.unlink()

    def _calculate_total_chunks(self, file_size: int) -> int:
        """Calculate total number of chunks needed"""
        return (file_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE

    async def _assemble_chunks(self, session: MediaUploadSession) -> Path:
        """Assemble chunks into final file"""

        assembled_file = self.temp_dir / f"{session.session_id}_assembled"

        try:
            with open(assembled_file, 'wb') as assembled_f:
                for chunk_index in range(session.total_chunks):
                    chunk_file = self.temp_dir / f"{session.session_id}_chunk_{chunk_index}"

                    if not chunk_file.exists():
                        raise FileNotFoundError(f"Chunk {chunk_index} missing")

                    with open(chunk_file, 'rb') as chunk_f:
                        assembled_f.write(chunk_f.read())

            # Verify assembled file size
            assembled_size = assembled_file.stat().st_size
            if assembled_size != session.file_size:
                raise ValueError(f"Assembled file size mismatch: {assembled_size} != {session.file_size}")

            return assembled_file

        except Exception as e:
            if assembled_file.exists():
                assembled_file.unlink()
            raise

    async def _cleanup_session_files(self, session_id: str):
        """Clean up temporary files for a session"""

        try:
            # Remove chunk files
            for chunk_file in self.temp_dir.glob(f"{session_id}_chunk_*"):
                chunk_file.unlink()

            # Remove assembled file
            assembled_file = self.temp_dir / f"{session_id}_assembled"
            if assembled_file.exists():
                assembled_file.unlink()

            logger.debug(f"Cleaned up temporary files for session {session_id}")

        except Exception as e:
            logger.warning(f"Failed to cleanup files for session {session_id}: {e}")

    async def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """Clean up expired upload sessions and their files"""

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        async with get_async_db_context() as db:
            # Find expired sessions
            result = await db.execute(
                select(MediaUploadSession).where(
                    MediaUploadSession.created_at < cutoff_time,
                    MediaUploadSession.status.in_(["active", "failed", "cancelled"])
                )
            )
            expired_sessions = result.scalars().all()

            for session in expired_sessions:
                try:
                    # Cleanup files
                    await self._cleanup_session_files(session.session_id)

                    # Update session status
                    session.status = "expired"

                    logger.info(f"Cleaned up expired session {session.session_id}")

                except Exception as e:
                    logger.error(f"Failed to cleanup expired session {session.session_id}: {e}")

            await db.commit()

        logger.info(f"Cleaned up {len(expired_sessions)} expired upload sessions")

    async def get_upload_statistics(self) -> Dict[str, Any]:
        """Get upload statistics"""

        async with get_async_db_context() as db:
            from sqlalchemy import func

            # Total sessions
            total_result = await db.execute(
                select(func.count(MediaUploadSession.id))
            )
            total_sessions = total_result.scalar() or 0

            # Sessions by status
            status_result = await db.execute(
                select(MediaUploadSession.status, func.count(MediaUploadSession.id))
                .group_by(MediaUploadSession.status)
            )
            status_counts = dict(status_result.fetchall())

            # Average file size
            avg_size_result = await db.execute(
                select(func.avg(MediaUploadSession.file_size))
                .where(MediaUploadSession.status == "completed")
            )
            avg_file_size = avg_size_result.scalar() or 0

            # Total bytes processed
            total_bytes_result = await db.execute(
                select(func.sum(MediaUploadSession.file_size))
                .where(MediaUploadSession.status == "completed")
            )
            total_bytes = total_bytes_result.scalar() or 0

            return {
                "total_sessions": total_sessions,
                "status_distribution": status_counts,
                "average_file_size_mb": round(avg_file_size / (1024 * 1024), 2),
                "total_bytes_processed_gb": round(total_bytes / (1024 * 1024 * 1024), 2),
                "temp_dir_size_mb": self._get_temp_dir_size()
            }

    def _get_temp_dir_size(self) -> float:
        """Calculate size of temporary directory"""
        total_size = 0
        try:
            for file_path in self.temp_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception:
            pass

        return round(total_size / (1024 * 1024), 2)  # MB