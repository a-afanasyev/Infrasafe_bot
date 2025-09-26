"""
Главное FastAPI приложение для Media Service
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time

from app.core.config import settings
from app.db.database import init_db, check_db_connection
from app.api.v1.router import api_router
from app.schemas import ErrorResponse, ValidationErrorResponse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Жизненный цикл приложения
    """
    # Startup
    logger.info("Starting Media Service...")

    try:
        # Инициализация базы данных
        await init_db()
        logger.info("Database initialized successfully")

        # Проверка подключения к БД
        if not check_db_connection():
            logger.error("Database connection failed!")
            raise RuntimeError("Database connection failed")

        logger.info("Media Service started successfully")

    except Exception as e:
        logger.error(f"Failed to start Media Service: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Media Service...")


# Создание FastAPI приложения
app = FastAPI(
    title="UK Media Service",
    description="Микросервис для управления медиа-файлами через Telegram каналы",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.allowed_origins == "*" else [settings.allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Добавляем сжатие
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Логируем запрос
    logger.info(f"Request: {request.method} {request.url.path}")

    # Выполняем запрос
    response = await call_next(request)

    # Логируем время выполнения
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} - {process_time:.3f}s")

    return response


# Обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Обработчик HTTP исключений
    """
    logger.warning(f"HTTP error {exc.status_code}: {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=exc.detail
        ).model_dump()
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Обработчик ошибок валидации
    """
    logger.warning(f"Validation error: {exc.errors()}")

    return JSONResponse(
        status_code=422,
        content=ValidationErrorResponse(
            message="Ошибка валидации данных",
            errors=exc.errors()
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Общий обработчик исключений
    """
    logger.error(f"Unexpected error: {exc}", exc_info=True)

    if settings.debug:
        error_detail = str(exc)
    else:
        error_detail = "Внутренняя ошибка сервера"

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message=error_detail
        ).model_dump()
    )


# Подключение роутеров
app.include_router(api_router)


# Корневой эндпоинт
@app.get("/")
async def root():
    """
    Корневой эндпоинт
    """
    return {
        "service": "UK Media Service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.debug else "disabled in production"
    }


# Эндпоинт для проверки версии
@app.get("/version")
async def version():
    """
    Информация о версии сервиса
    """
    return {
        "service": "UK Media Service",
        "version": "1.0.0",
        "build": "production",
        "debug": settings.debug
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )