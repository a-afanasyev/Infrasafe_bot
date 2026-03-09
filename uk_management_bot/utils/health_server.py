"""
HTTP Health Check Server для Docker health checks
"""
import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Dict, Any
import time

from uk_management_bot.database.session import SessionLocal

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
        """Обработка /health endpoint — purely synchronous, no event loop creation"""
        db = None
        try:
            from sqlalchemy import text as sa_text
            db = SessionLocal()

            # Synchronous DB ping
            start = time.time()
            db.execute(sa_text("SELECT 1"))
            db_ms = round((time.time() - start) * 1000, 2)

            health_data = {
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {
                    'database': {
                        'status': 'healthy',
                        'response_time_ms': db_ms,
                    }
                }
            }
            self._send_json_response(health_data, 200)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self._send_json_response({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }, 503)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
    
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