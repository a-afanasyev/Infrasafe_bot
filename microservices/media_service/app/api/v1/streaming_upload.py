"""
Streaming Upload API endpoints
Optimized endpoints for large file uploads using streaming
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse

from app.services.async_media_storage import AsyncMediaStorageService
from app.services.streaming_upload import streaming_upload_service
from app.schemas.media import MediaFileResponse, MediaUploadResponse
from app.core.auth import get_current_user, require_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload/stream", response_model=MediaUploadResponse)
async def stream_upload_media(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request_number: str = Form(...),
    category: str = Form(default="request_photo"),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string or comma-separated
    uploaded_by: Optional[int] = Form(None),
    current_user: dict = Depends(require_api_key)
):
    """
    Stream upload large media files without loading into memory
    Uses temporary file storage and background processing
    """
    logger.info(f"Starting stream upload for request {request_number}")

    try:
        # Parse tags
        parsed_tags = []
        if tags:
            try:
                import json
                parsed_tags = json.loads(tags)
            except:
                # Fallback to comma-separated
                parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Stream file to temporary storage
        file_info = await streaming_upload_service.stream_upload_to_temp(
            upload_file=file,
            max_size=None  # Use default from settings
        )

        # Create Telegram InputFile from temp file
        telegram_file = await streaming_upload_service.create_telegram_input_file(
            file_info["temp_path"],
            file_info["filename"]
        )

        # Initialize async media storage service
        media_service = AsyncMediaStorageService()

        # Read file content for upload (still need bytes for Telegram)
        # TODO: Optimize this to stream directly to Telegram
        with open(file_info["temp_path"], "rb") as f:
            file_data = f.read()

        # Upload to media service
        media_file = await media_service.upload_request_media(
            request_number=request_number,
            file_data=file_data,
            filename=file_info["filename"],
            content_type=file_info["content_type"],
            category=category,
            description=description,
            tags=parsed_tags,
            uploaded_by=uploaded_by
        )

        # Schedule cleanup of temporary file
        background_tasks.add_task(
            streaming_upload_service.cleanup_temp_file,
            file_info["temp_path"],
            file_info.get("temp_fd")
        )

        return MediaUploadResponse(
            success=True,
            media_file_id=media_file.id,
            filename=media_file.filename,
            file_size=media_file.file_size,
            telegram_message_id=media_file.telegram_message_id,
            message="File uploaded successfully via streaming"
        )

    except ValueError as e:
        logger.warning(f"Validation error in stream upload: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Stream upload failed: {e}")
        # Ensure cleanup on error
        if 'file_info' in locals():
            await streaming_upload_service.cleanup_temp_file(
                file_info["temp_path"],
                file_info.get("temp_fd")
            )
        raise HTTPException(status_code=500, detail="Upload failed")


@router.post("/upload/stream/multiple", response_model=List[MediaUploadResponse])
async def stream_upload_multiple_media(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    request_number: str = Form(...),
    category: str = Form(default="request_photo"),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    uploaded_by: Optional[int] = Form(None),
    current_user: dict = Depends(require_api_key)
):
    """
    Stream upload multiple files efficiently
    """
    logger.info(f"Starting multi-file stream upload for request {request_number}, {len(files)} files")

    if len(files) > 10:  # Configurable limit
        raise HTTPException(status_code=400, detail="Too many files. Maximum 10 files per request.")

    results = []
    temp_files = []

    try:
        # Parse tags once
        parsed_tags = []
        if tags:
            try:
                import json
                parsed_tags = json.loads(tags)
            except:
                parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

        media_service = AsyncMediaStorageService()

        for i, file in enumerate(files):
            try:
                logger.info(f"Processing file {i+1}/{len(files)}: {file.filename}")

                # Stream each file to temp storage
                file_info = await streaming_upload_service.stream_upload_to_temp(
                    upload_file=file,
                    max_size=None
                )
                temp_files.append(file_info)

                # Read file for upload
                with open(file_info["temp_path"], "rb") as f:
                    file_data = f.read()

                # Upload to media service
                media_file = await media_service.upload_request_media(
                    request_number=request_number,
                    file_data=file_data,
                    filename=file_info["filename"],
                    content_type=file_info["content_type"],
                    category=category,
                    description=f"{description} (File {i+1})" if description else f"File {i+1}",
                    tags=parsed_tags,
                    uploaded_by=uploaded_by
                )

                results.append(MediaUploadResponse(
                    success=True,
                    media_file_id=media_file.id,
                    filename=media_file.filename,
                    file_size=media_file.file_size,
                    telegram_message_id=media_file.telegram_message_id,
                    message=f"File {i+1} uploaded successfully"
                ))

            except Exception as e:
                logger.error(f"Failed to upload file {i+1} ({file.filename}): {e}")
                results.append(MediaUploadResponse(
                    success=False,
                    filename=file.filename,
                    message=f"Upload failed: {str(e)}"
                ))

        # Schedule cleanup of all temp files
        for file_info in temp_files:
            background_tasks.add_task(
                streaming_upload_service.cleanup_temp_file,
                file_info["temp_path"],
                file_info.get("temp_fd")
            )

        logger.info(f"Multi-file upload completed: {len(results)} files processed")
        return results

    except Exception as e:
        logger.error(f"Multi-file stream upload failed: {e}")
        # Cleanup all temp files on error
        for file_info in temp_files:
            await streaming_upload_service.cleanup_temp_file(
                file_info["temp_path"],
                file_info.get("temp_fd")
            )
        raise HTTPException(status_code=500, detail="Multi-file upload failed")


@router.post("/upload/stream/progress", response_model=MediaUploadResponse)
async def stream_upload_with_progress(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request_number: str = Form(...),
    category: str = Form(default="request_photo"),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    uploaded_by: Optional[int] = Form(None),
    current_user: dict = Depends(require_api_key)
):
    """
    Stream upload with progress tracking
    """
    progress_info = {"chunks": 0, "bytes": 0}

    async def progress_callback(chunks_processed: int, bytes_processed: int, filename: str):
        progress_info["chunks"] = chunks_processed
        progress_info["bytes"] = bytes_processed
        logger.debug(f"Upload progress: {bytes_processed} bytes, {chunks_processed} chunks")

    try:
        # Parse tags
        parsed_tags = []
        if tags:
            try:
                import json
                parsed_tags = json.loads(tags)
            except:
                parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Stream with progress
        file_info = await streaming_upload_service.stream_upload_with_progress(
            upload_file=file,
            progress_callback=progress_callback,
            max_size=None
        )

        media_service = AsyncMediaStorageService()

        # Read file for upload
        with open(file_info["temp_path"], "rb") as f:
            file_data = f.read()

        # Upload to media service
        media_file = await media_service.upload_request_media(
            request_number=request_number,
            file_data=file_data,
            filename=file_info["filename"],
            content_type=file_info["content_type"],
            category=category,
            description=description,
            tags=parsed_tags,
            uploaded_by=uploaded_by
        )

        # Schedule cleanup
        background_tasks.add_task(
            streaming_upload_service.cleanup_temp_file,
            file_info["temp_path"],
            file_info.get("temp_fd")
        )

        return MediaUploadResponse(
            success=True,
            media_file_id=media_file.id,
            filename=media_file.filename,
            file_size=media_file.file_size,
            telegram_message_id=media_file.telegram_message_id,
            message=f"File uploaded successfully. Processed {progress_info['chunks']} chunks."
        )

    except Exception as e:
        logger.error(f"Progress upload failed: {e}")
        if 'file_info' in locals():
            await streaming_upload_service.cleanup_temp_file(
                file_info["temp_path"],
                file_info.get("temp_fd")
            )
        raise HTTPException(status_code=500, detail="Upload failed")


@router.get("/upload/limits")
async def get_upload_limits(current_user: dict = Depends(require_api_key)):
    """
    Get current upload limits and configuration
    """
    from app.core.config import settings

    return {
        "max_file_size": settings.max_file_size,
        "max_files_per_request": settings.max_files_per_request,
        "allowed_file_types": settings.allowed_file_types,
        "streaming_available": True,
        "chunk_size": 8192  # Default chunk size
    }