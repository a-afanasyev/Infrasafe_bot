"""
Веб-приложение для регистрации по приглашениям
"""
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import os
import sys

# Добавляем путь к основному приложению
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from uk_management_bot.web.api.invite import router as invite_router
from uk_management_bot.web.limiter import web_limiter
from uk_management_bot.config.settings import settings

app = FastAPI(title="UK Management Bot - Web Registration", version="1.0.0")

# Rate limiting (shared instance from limiter.py)
app.state.limiter = web_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restrict to known origins
_web_origins = ["https://web.telegram.org"]
if settings.DEBUG:
    _web_origins.extend(["http://localhost:3000", "http://localhost:5173"])
if settings.FRONTEND_URL:
    _web_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_web_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Middleware для заголовков Telegram Web App
@app.middleware("http")
async def add_telegram_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Заголовки для Telegram Web App
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://web.telegram.org https://telegram.org; script-src 'self' 'unsafe-inline' https://telegram.org; style-src 'self' 'unsafe-inline'"
    
    return response

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="uk_management_bot/web/static"), name="static")

# Настройка шаблонов
templates = Jinja2Templates(directory="uk_management_bot/web/templates")

# Подключаем API роутеры
app.include_router(invite_router, prefix="/api")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/register/{token}", response_class=HTMLResponse)
async def register_page(request: Request, token: str):
    """Страница регистрации по приглашению"""
    return templates.TemplateResponse("register.html", {
        "request": request,
        "token": token
    })

@app.get("/test", response_class=HTMLResponse)
async def test_page(request: Request):
    """Тестовая страница для проверки Telegram Web App"""
    return templates.TemplateResponse("test.html", {"request": request})

@app.get("/simple", response_class=HTMLResponse)
async def simple_test_page(request: Request):
    """Простая тестовая страница для проверки Telegram Web App"""
    return templates.TemplateResponse("simple_test.html", {"request": request})

@app.get("/minimal", response_class=HTMLResponse)
async def minimal_test_page(request: Request):
    """Минимальная тестовая страница без внешних зависимостей"""
    return templates.TemplateResponse("minimal_test.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
