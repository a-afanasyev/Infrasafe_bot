"""
HTTP Health Check Server для Docker health checks
"""
import asyncio
import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Dict, Any
import time

from sqlalchemy.orm import Session
from uk_management_bot.database.session import SessionLocal
from uk_management_bot.handlers.health import get_health_status

logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler для health check запросов"""
    
    def log_message(self, format, *args):
        """Отключаем стандартные логи HTTP сервера"""
        pass
    
    def do_GET(self):
        """Обработка GET запросов"""
        if self.path == '/health':
            self._handle_health_check()
        elif self.path == '/ping':
            self._handle_ping()
        else:
            self._send_404()
    
    def _handle_health_check(self):
        """Обработка /health endpoint"""
        try:
            # Создаем сессию БД
            db = SessionLocal()
            loop = None
            try:
                # Получаем статус системы
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                health_data = loop.run_until_complete(get_health_status(db))

                # Определяем HTTP статус код
                status_code = 200
                if health_data.get('status') == 'unhealthy':
                    status_code = 503  # Service Unavailable
                elif health_data.get('status') == 'degraded':
                    status_code = 200  # Still OK, but with warnings

                self._send_json_response(health_data, status_code)

            finally:
                db.close()
                # Закрываем event loop только если он был создан
                if loop is not None and not loop.is_closed():
                    try:
                        # Закрываем все pending задачи
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        # Даем время на завершение задач
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception as e:
                        logger.debug(f"Error cleaning up loop tasks: {e}")
                    finally:
                        loop.close()
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self._send_json_response({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }, 503)
    
    def _handle_ping(self):
        """Обработка /ping endpoint - простая проверка доступности"""
        self._send_json_response({
            'status': 'ok',
            'message': 'pong',
            'timestamp': datetime.utcnow().isoformat()
        }, 200)
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        """Отправка JSON ответа"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        
        json_data = json.dumps(data, indent=2, ensure_ascii=False)
        self.wfile.write(json_data.encode('utf-8'))
    
    def _send_404(self):
        """Отправка 404 ответа"""
        self.send_response(404)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            'error': 'Not Found',
            'message': 'Available endpoints: /health, /ping',
            'timestamp': datetime.utcnow().isoformat()
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))


class HealthServer:
    """HTTP сервер для health check"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8000):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.running = False
    
    def start(self):
        """Запуск health check сервера в отдельном потоке"""
        if self.running:
            logger.warning("Health server is already running")
            return
        
        try:
            self.server = HTTPServer((self.host, self.port), HealthCheckHandler)
            self.thread = Thread(target=self._run_server, daemon=True)
            self.thread.start()
            self.running = True
            logger.info(f"Health check server started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise
    
    def _run_server(self):
        """Запуск сервера в потоке"""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Health server error: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Остановка health check сервера"""
        if not self.running:
            return
        
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
                logger.info("Health check server stopped")
        except Exception as e:
            logger.error(f"Error stopping health server: {e}")
        finally:
            self.running = False


# Глобальный экземпляр сервера
_health_server = None

def start_health_server(host: str = '0.0.0.0', port: int = 8000):
    """Запуск глобального health check сервера"""
    global _health_server
    
    if _health_server is not None:
        logger.warning("Health server already exists")
        return _health_server
    
    _health_server = HealthServer(host, port)
    _health_server.start()
    return _health_server

def stop_health_server():
    """Остановка глобального health check сервера"""
    global _health_server
    
    if _health_server is not None:
        _health_server.stop()
        _health_server = None

def get_health_server() -> HealthServer:
    """Получение экземпляра health сервера"""
    return _health_server