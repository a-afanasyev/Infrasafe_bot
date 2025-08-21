"""
Google Sheets Utilities

Утилиты для работы с Google Sheets API:
- Circuit Breaker для защиты от API лимитов
- Rate Limiter для контроля частоты запросов
"""

import time
import asyncio
from typing import Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class CircuitBreaker:
    """
    Предохранитель для защиты от API лимитов Google Sheets
    
    Реализует паттерн Circuit Breaker для предотвращения каскадных сбоев
    при проблемах с Google Sheets API.
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Инициализация Circuit Breaker
        
        Args:
            failure_threshold: Количество ошибок для перехода в OPEN состояние
            recovery_timeout: Время ожидания перед переходом в HALF_OPEN (секунды)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
        logger.info("Circuit Breaker initialized", 
                   failure_threshold=failure_threshold,
                   recovery_timeout=recovery_timeout)
    
    def is_closed(self) -> bool:
        """
        Проверка, можно ли выполнять операции
        
        Returns:
            True если операции разрешены, False если заблокированы
        """
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Проверяем, прошло ли достаточно времени для восстановления
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit Breaker transitioning to HALF_OPEN state")
                return True
            return False
        return True  # HALF_OPEN
    
    def on_success(self):
        """Обработка успешной операции"""
        if self.state == "HALF_OPEN":
            # Если операция успешна в HALF_OPEN состоянии, переходим в CLOSED
            self.state = "CLOSED"
            self.failure_count = 0
            logger.info("Circuit Breaker transitioning to CLOSED state after successful operation")
        elif self.state == "CLOSED":
            # Сбрасываем счетчик ошибок при успешных операциях
            self.failure_count = 0
    
    def on_error(self):
        """Обработка ошибки операции"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning("Circuit Breaker error", 
                      failure_count=self.failure_count,
                      threshold=self.failure_threshold,
                      state=self.state)
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.error("Circuit Breaker transitioning to OPEN state",
                        failure_count=self.failure_count,
                        threshold=self.failure_threshold)
    
    def get_state(self) -> Dict[str, Any]:
        """Получение текущего состояния Circuit Breaker"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout,
            "is_closed": self.is_closed()
        }


class RateLimiter:
    """
    Ограничитель скорости для Google Sheets API
    
    Контролирует частоту запросов к Google Sheets API для соблюдения лимитов.
    """
    
    def __init__(self, requests_per_minute: int = 60):
        """
        Инициализация Rate Limiter
        
        Args:
            requests_per_minute: Максимальное количество запросов в минуту
        """
        self.requests_per_minute = requests_per_minute
        self.request_times = []
        
        logger.info("Rate Limiter initialized", 
                   requests_per_minute=requests_per_minute)
    
    async def wait_if_needed(self):
        """
        Ожидание, если превышен лимит запросов
        
        Блокирует выполнение до тех пор, пока не освободится слот для запроса.
        """
        now = time.time()
        
        # Удаляем старые запросы (старше 60 секунд)
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        # Если достигнут лимит, ждем
        if len(self.request_times) >= self.requests_per_minute:
            # Вычисляем время до освобождения первого слота
            wait_time = 60 - (now - self.request_times[0])
            if wait_time > 0:
                logger.info("Rate limit reached, waiting", 
                           wait_time=wait_time,
                           current_requests=len(self.request_times),
                           limit=self.requests_per_minute)
                await asyncio.sleep(wait_time)
        
        # Добавляем текущий запрос
        self.request_times.append(time.time())
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Получение статистики использования"""
        now = time.time()
        recent_requests = [t for t in self.request_times if now - t < 60]
        
        return {
            "requests_per_minute": self.requests_per_minute,
            "current_requests": len(recent_requests),
            "available_requests": max(0, self.requests_per_minute - len(recent_requests)),
            "usage_percentage": (len(recent_requests) / self.requests_per_minute) * 100
        }


class SheetsSyncWorker:
    """
    Фоновый обработчик синхронизации с Google Sheets
    
    Обрабатывает задачи синхронизации из очереди с применением
    Circuit Breaker и Rate Limiter.
    """
    
    def __init__(self, sheets_service, queue, circuit_breaker: CircuitBreaker = None, 
                 rate_limiter: RateLimiter = None):
        """
        Инициализация SheetsSyncWorker
        
        Args:
            sheets_service: Экземпляр SheetsService
            queue: Очередь задач синхронизации
            circuit_breaker: Экземпляр Circuit Breaker
            rate_limiter: Экземпляр Rate Limiter
        """
        self.sheets_service = sheets_service
        self.queue = queue
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.running = False
        
        logger.info("SheetsSyncWorker initialized")
    
    async def start(self):
        """Запуск обработчика"""
        self.running = True
        logger.info("SheetsSyncWorker started")
        
        while self.running:
            try:
                # Получаем задачу из очереди
                task = await self.queue.get()
                await self.process_task(task)
                
            except asyncio.CancelledError:
                logger.info("SheetsSyncWorker cancelled")
                break
            except Exception as e:
                logger.error("Error in SheetsSyncWorker main loop", error=str(e))
                await asyncio.sleep(1)  # Небольшая пауза перед следующей итерацией
    
    async def stop(self):
        """Остановка обработчика"""
        self.running = False
        logger.info("SheetsSyncWorker stopped")
    
    async def process_task(self, task):
        """
        Обработка задачи синхронизации
        
        Args:
            task: Задача синхронизации (SyncTask)
        """
        try:
            # Проверяем Circuit Breaker
            if not self.circuit_breaker.is_closed():
                logger.warning("Circuit Breaker is open, returning task to queue",
                              task_id=task.request_id,
                              task_type=task.task_type)
                await self.queue.put(task)  # Возвращаем задачу в очередь
                return
            
            # Проверяем Rate Limiter
            await self.rate_limiter.wait_if_needed()
            
            # Выполняем синхронизацию
            success = False
            if task.task_type == "create":
                success = await self.sheets_service.create_request_in_sheets(task.data)
            elif task.task_type == "update":
                success = await self.sheets_service.update_request_in_sheets(task.request_id, task.data)
            else:
                logger.warning("Unknown task type", task_type=task.task_type)
                return
            
            # Обновляем состояние Circuit Breaker
            if success:
                self.circuit_breaker.on_success()
                logger.info("Task processed successfully",
                           task_id=task.request_id,
                           task_type=task.task_type)
            else:
                self.circuit_breaker.on_error()
                await self.handle_error(task, "Sync operation failed")
                
        except Exception as e:
            self.circuit_breaker.on_error()
            await self.handle_error(task, str(e))
    
    async def handle_error(self, task, error_message: str):
        """
        Обработка ошибок синхронизации
        
        Args:
            task: Задача, которая вызвала ошибку
            error_message: Сообщение об ошибке
        """
        task.retry_count += 1
        max_retries = 3
        
        logger.error("Sync task error",
                    task_id=task.request_id,
                    task_type=task.task_type,
                    error=error_message,
                    retry_count=task.retry_count,
                    max_retries=max_retries)
        
        # Если не превышен лимит попыток, возвращаем задачу в очередь
        if task.retry_count < max_retries:
            # Экспоненциальная задержка перед повторной попыткой
            delay = min(60, 2 ** task.retry_count)  # Максимум 60 секунд
            await asyncio.sleep(delay)
            await self.queue.put(task)
            logger.info("Task returned to queue for retry",
                       task_id=task.request_id,
                       retry_count=task.retry_count,
                       delay=delay)
        else:
            logger.error("Task failed after maximum retries",
                        task_id=task.request_id,
                        task_type=task.task_type,
                        final_error=error_message)
    
    def get_status(self) -> Dict[str, Any]:
        """Получение статуса обработчика"""
        return {
            "running": self.running,
            "circuit_breaker": self.circuit_breaker.get_state(),
            "rate_limiter": self.rate_limiter.get_usage_stats()
        }
