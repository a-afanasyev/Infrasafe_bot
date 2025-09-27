"""
Streaming File Upload Service
Optimized file handling for large media uploads without loading entire files into memory
"""

import logging
import os
import tempfile
import aiofiles
from typing import AsyncGenerator, Optional, Dict, Any
from fastapi import UploadFile
from aiogram.types import InputFile, FSInputFile

from app.core.config import settings

logger = logging.getLogger(__name__)


class StreamingUploadService:
    """
    Service for handling streaming file uploads to minimize memory usage
    """

    def __init__(self, chunk_size: int = 8192):
        self.chunk_size = chunk_size
        self.temp_dir = tempfile.gettempdir()

    async def stream_upload_to_temp(
        self,
        upload_file: UploadFile,
        max_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Stream upload file to temporary storage
        Returns file info including path and metadata
        """
        if max_size is None:
            max_size = settings.max_file_size

        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=f"_{upload_file.filename}",
            dir=self.temp_dir
        )

        total_size = 0
        file_hash = ""

        try:
            # Use aiofiles for async file operations
            async with aiofiles.open(temp_path, 'wb') as temp_file:
                # Stream file in chunks
                async for chunk in self._read_chunks(upload_file, max_size):
                    total_size += len(chunk)
                    await temp_file.write(chunk)

                    # Check size limit during streaming
                    if total_size > max_size:
                        raise ValueError(f"File size exceeds limit: {total_size} > {max_size}")

            # Validate file type after streaming
            await self._validate_file_type(temp_path, upload_file.content_type)

            return {
                "temp_path": temp_path,
                "filename": upload_file.filename,
                "content_type": upload_file.content_type,
                "size": total_size,
                "temp_fd": temp_fd
            }

        except Exception as e:
            # Cleanup on error
            try:
                os.close(temp_fd)
                os.unlink(temp_path)
            except:
                pass
            raise e

    async def _read_chunks(
        self,
        upload_file: UploadFile,
        max_size: int
    ) -> AsyncGenerator[bytes, None]:
        """
        Async generator to read file in chunks
        """
        total_read = 0

        while True:
            chunk = await upload_file.read(self.chunk_size)
            if not chunk:
                break

            total_read += len(chunk)
            if total_read > max_size:
                raise ValueError(f"File size exceeds limit during streaming: {total_read} > {max_size}")

            yield chunk

    async def _validate_file_type(self, temp_path: str, declared_content_type: str):
        """
        Validate file type by reading file headers (magic bytes)
        """
        try:
            # Read first few bytes to determine actual file type
            async with aiofiles.open(temp_path, 'rb') as f:
                magic_bytes = await f.read(512)

            actual_content_type = self._detect_content_type(magic_bytes)

            # Check if declared type matches actual type
            if actual_content_type and actual_content_type != declared_content_type:
                logger.warning(
                    f"Content type mismatch: declared={declared_content_type}, "
                    f"actual={actual_content_type}"
                )

            # Validate against allowed types
            content_type_to_check = actual_content_type or declared_content_type
            if content_type_to_check not in settings.allowed_file_types:
                raise ValueError(f"File type not allowed: {content_type_to_check}")

        except Exception as e:
            logger.error(f"File validation failed: {e}")
            raise

    def _detect_content_type(self, magic_bytes: bytes) -> Optional[str]:
        """
        Detect content type from magic bytes
        """
        # Common file type signatures
        signatures = {
            b'\xFF\xD8\xFF': 'image/jpeg',
            b'\x89PNG\r\n\x1a\n': 'image/png',
            b'GIF87a': 'image/gif',
            b'GIF89a': 'image/gif',
            b'\x00\x00\x00\x18ftypmp4': 'video/mp4',
            b'\x00\x00\x00\x20ftypmp4': 'video/mp4',
            b'\x00\x00\x00\x1Cftypmp4': 'video/mp4',
        }

        for signature, content_type in signatures.items():
            if magic_bytes.startswith(signature):
                return content_type

        # Check for MP4 variants
        if b'ftyp' in magic_bytes[:32]:
            if b'mp4' in magic_bytes[:32] or b'M4V' in magic_bytes[:32]:
                return 'video/mp4'

        return None

    async def create_telegram_input_file(self, temp_path: str, filename: str) -> InputFile:
        """
        Create Telegram InputFile from temporary file without loading into memory
        """
        return FSInputFile(temp_path, filename=filename)

    async def cleanup_temp_file(self, temp_path: str, temp_fd: Optional[int] = None):
        """
        Cleanup temporary file
        """
        try:
            if temp_fd is not None:
                os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.debug(f"Cleaned up temporary file: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary file {temp_path}: {e}")

    async def stream_upload_with_progress(
        self,
        upload_file: UploadFile,
        progress_callback: Optional[callable] = None,
        max_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Stream upload with progress tracking
        """
        if max_size is None:
            max_size = settings.max_file_size

        temp_fd, temp_path = tempfile.mkstemp(
            suffix=f"_{upload_file.filename}",
            dir=self.temp_dir
        )

        total_size = 0
        chunks_processed = 0

        try:
            async with aiofiles.open(temp_path, 'wb') as temp_file:
                async for chunk in self._read_chunks(upload_file, max_size):
                    total_size += len(chunk)
                    chunks_processed += 1
                    await temp_file.write(chunk)

                    # Call progress callback if provided
                    if progress_callback:
                        await progress_callback(
                            chunks_processed=chunks_processed,
                            bytes_processed=total_size,
                            filename=upload_file.filename
                        )

            await self._validate_file_type(temp_path, upload_file.content_type)

            return {
                "temp_path": temp_path,
                "filename": upload_file.filename,
                "content_type": upload_file.content_type,
                "size": total_size,
                "temp_fd": temp_fd,
                "chunks_processed": chunks_processed
            }

        except Exception as e:
            # Cleanup on error
            await self.cleanup_temp_file(temp_path, temp_fd)
            raise e

    async def get_file_metadata(self, temp_path: str) -> Dict[str, Any]:
        """
        Extract metadata from uploaded file
        """
        try:
            stat = os.stat(temp_path)

            # Basic metadata
            metadata = {
                "size": stat.st_size,
                "created_at": stat.st_ctime,
                "modified_at": stat.st_mtime,
            }

            # Try to get additional metadata based on file type
            async with aiofiles.open(temp_path, 'rb') as f:
                magic_bytes = await f.read(512)

            content_type = self._detect_content_type(magic_bytes)
            if content_type:
                metadata["detected_content_type"] = content_type

                # Add type-specific metadata
                if content_type.startswith('image/'):
                    metadata.update(await self._get_image_metadata(temp_path))
                elif content_type.startswith('video/'):
                    metadata.update(await self._get_video_metadata(temp_path))

            return metadata

        except Exception as e:
            logger.warning(f"Failed to extract metadata from {temp_path}: {e}")
            return {"size": 0}

    async def _get_image_metadata(self, temp_path: str) -> Dict[str, Any]:
        """
        Extract image-specific metadata
        """
        try:
            # This would require PIL/Pillow for full implementation
            # For now, return basic info
            return {
                "type": "image",
                "format": "unknown"
            }
        except Exception:
            return {}

    async def _get_video_metadata(self, temp_path: str) -> Dict[str, Any]:
        """
        Extract video-specific metadata
        """
        try:
            # This would require ffmpeg-python for full implementation
            # For now, return basic info
            return {
                "type": "video",
                "format": "unknown"
            }
        except Exception:
            return {}


# Global instance
streaming_upload_service = StreamingUploadService()