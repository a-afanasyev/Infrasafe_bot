"""
Сервис передачи заявок между сменами
Обеспечивает непрерывность обслуживания при смене дежурного персонала
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class TransferStatus(Enum):
    """Статусы передачи заявок"""
    PENDING = "pending"           # Ожидает передачи
    IN_PROGRESS = "in_progress"   # В процессе передачи
    COMPLETED = "completed"       # Передача завершена
    FAILED = "failed"            # Ошибка передачи
    CANCELLED = "cancelled"       # Передача отменена


@dataclass
class TransferItem:
    """Элемент передачи - одна заявка"""
    request_id: int
    request_category: str
    request_status: str
    request_address: str
    priority: str
    assigned_at: datetime
    notes: Optional[str] = None
    transfer_notes: Optional[str] = None  # Комментарий при передаче


@dataclass
class ShiftTransfer:
    """Передача заявок между сменами"""
    id: Optional[int]
    outgoing_shift_id: int
    incoming_shift_id: int
    outgoing_executor_id: int
    incoming_executor_id: int
    
    transfer_items: List[TransferItem]
    status: TransferStatus
    
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    transfer_notes: Optional[str] = None
    
    # Статистика
    total_requests: int = 0
    transferred_requests: int = 0
    failed_requests: int = 0


class ShiftTransferService:
    """Сервис для управления передачей заявок между сменами"""
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ПЕРЕДАЧИ ==========
    
    def initiate_shift_transfer(
        self, 
        outgoing_shift_id: int, 
        incoming_shift_id: int,
        initiated_by: int
    ) -> Optional[ShiftTransfer]:
        """
        Инициирует передачу заявок между сменами
        
        Args:
            outgoing_shift_id: ID завершающейся смены
            incoming_shift_id: ID начинающейся смены
            initiated_by: ID пользователя, инициирующего передачу
        
        Returns:
            ShiftTransfer или None при ошибке
        """
        try:
            logger.info(f"Инициация передачи смен: {outgoing_shift_id} → {incoming_shift_id}")
            
            # Получаем смены
            outgoing_shift = self.db.query(Shift).filter(Shift.id == outgoing_shift_id).first()
            incoming_shift = self.db.query(Shift).filter(Shift.id == incoming_shift_id).first()
            
            if not outgoing_shift or not incoming_shift:
                logger.error("Одна или обе смены не найдены")
                return None
            
            # Проверяем статусы смен
            if outgoing_shift.status not in ["active", "in_transition"]:
                logger.error(f"Неверный статус исходящей смены: {outgoing_shift.status}")
                return None
            
            if incoming_shift.status != "planned":
                logger.error(f"Неверный статус входящей смены: {incoming_shift.status}")
                return None
            
            # Получаем активные заявки для передачи
            transfer_items = self._get_requests_for_transfer(outgoing_shift)
            
            if not transfer_items:
                logger.info("Нет заявок для передачи")
                return self._create_empty_transfer(outgoing_shift, incoming_shift)
            
            # Создаем объект передачи
            transfer = ShiftTransfer(
                id=None,
                outgoing_shift_id=outgoing_shift_id,
                incoming_shift_id=incoming_shift_id,
                outgoing_executor_id=outgoing_shift.executor_id,
                incoming_executor_id=incoming_shift.executor_id,
                transfer_items=transfer_items,
                status=TransferStatus.PENDING,
                total_requests=len(transfer_items)
            )
            
            # Меняем статусы смен
            outgoing_shift.status = "in_transition"
            incoming_shift.status = "planned"  # Остается запланированной до завершения передачи
            
            # Создаем записи аудита
            self._create_transfer_audit(transfer, initiated_by, "initiated")
            
            # Отправляем уведомления
            self._notify_transfer_initiated(transfer)
            
            self.db.commit()
            logger.info(f"Передача инициирована: {len(transfer_items)} заявок")
            
            return transfer
            
        except Exception as e:
            logger.error(f"Ошибка инициации передачи: {e}")
            self.db.rollback()
            return None
    
    def _get_requests_for_transfer(self, shift: Shift) -> List[TransferItem]:
        """Получает заявки, которые нужно передать"""
        try:
            # Ищем все активные заявки, назначенные на эту смену или исполнителю
            active_statuses = ["В работе", "Закуп", "Уточнение", "Принята"]
            
            requests = self.db.query(Request).filter(
                and_(
                    Request.executor_id == shift.executor_id,
                    Request.status.in_(active_statuses),
                    Request.assigned_at >= shift.planned_start_time,
                    or_(
                        Request.assigned_at <= shift.planned_end_time,
                        shift.status == "active"  # Для активных смен берем все заявки исполнителя
                    )
                )
            ).order_by(Request.urgency.desc(), Request.created_at).all()
            
            transfer_items = []
            for request in requests:
                # Определяем приоритет передачи
                priority = "high" if request.urgency == "Критическая" else "medium" if request.urgency == "Высокая" else "normal"
                
                item = TransferItem(
                    request_id=request.request_number,
                    request_category=request.category,
                    request_status=request.status,
                    request_address=request.address[:50] + "..." if len(request.address) > 50 else request.address,
                    priority=priority,
                    assigned_at=request.assigned_at,
                    notes=request.notes
                )
                
                transfer_items.append(item)
            
            logger.info(f"Найдено {len(transfer_items)} заявок для передачи")
            return transfer_items
            
        except Exception as e:
            logger.error(f"Ошибка поиска заявок для передачи: {e}")
            return []
    
    def _create_empty_transfer(self, outgoing_shift: Shift, incoming_shift: Shift) -> ShiftTransfer:
        """Создает пустую передачу (нет активных заявок)"""
        transfer = ShiftTransfer(
            id=None,
            outgoing_shift_id=outgoing_shift.id,
            incoming_shift_id=incoming_shift.id,
            outgoing_executor_id=outgoing_shift.executor_id,
            incoming_executor_id=incoming_shift.executor_id,
            transfer_items=[],
            status=TransferStatus.COMPLETED,
            total_requests=0,
            transferred_requests=0,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            transfer_notes="Передача завершена автоматически - нет активных заявок"
        )
        
        # Завершаем исходящую смену и активируем входящую
        outgoing_shift.status = "completed"
        outgoing_shift.actual_end_time = datetime.now()
        incoming_shift.status = "active"
        incoming_shift.actual_start_time = datetime.now()
        
        return transfer
    
    def start_transfer_process(self, transfer: ShiftTransfer, executor_id: int) -> bool:
        """
        Начинает процесс передачи заявок
        
        Args:
            transfer: Объект передачи
            executor_id: ID исполнителя, начинающего передачу
        
        Returns:
            bool: True если процесс начат успешно
        """
        try:
            if transfer.status != TransferStatus.PENDING:
                logger.error(f"Неверный статус передачи для начала: {transfer.status}")
                return False
            
            if executor_id != transfer.outgoing_executor_id:
                logger.error(f"Передачу может начать только исходящий исполнитель")
                return False
            
            # Меняем статус передачи
            transfer.status = TransferStatus.IN_PROGRESS
            transfer.started_at = datetime.now()
            
            # Создаем аудит
            self._create_transfer_audit(transfer, executor_id, "started")
            
            # Уведомляем входящего исполнителя
            self._notify_transfer_started(transfer)
            
            logger.info(f"Процесс передачи начат исполнителем {executor_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка начала процесса передачи: {e}")
            return False
    
    def transfer_single_request(
        self, 
        transfer: ShiftTransfer, 
        request_id: int, 
        transfer_notes: Optional[str] = None,
        executor_id: int = None
    ) -> bool:
        """
        Передает одну заявку в рамках передачи смены
        
        Args:
            transfer: Объект передачи
            request_id: ID заявки для передачи
            transfer_notes: Комментарий к передаче
            executor_id: ID исполнителя, выполняющего передачу
        
        Returns:
            bool: True если заявка передана успешно
        """
        try:
            # Находим заявку в списке передачи
            transfer_item = None
            for item in transfer.transfer_items:
                if item.request_id == request_id:
                    transfer_item = item
                    break
            
            if not transfer_item:
                logger.error(f"Заявка {request_id} не найдена в списке передачи")
                return False
            
            # Получаем заявку из БД
            request = self.db.query(Request).filter(Request.id == request_id).first()
            if not request:
                logger.error(f"Заявка {request_id} не найдена в базе данных")
                return False
            
            # Переназначаем заявку на входящего исполнителя
            old_executor_id = request.executor_id
            request.executor_id = transfer.incoming_executor_id
            request.assigned_at = datetime.now()
            request.assigned_by = transfer.outgoing_executor_id  # Кто передал
            
            # Добавляем комментарий о передаче
            if transfer_notes:
                transfer_item.transfer_notes = transfer_notes
                existing_notes = request.notes or ""
                transfer_comment = f"\n[ПЕРЕДАЧА СМЕНЫ {datetime.now().strftime('%d.%m.%Y %H:%M')}] {transfer_notes}"
                request.notes = existing_notes + transfer_comment
            
            # Обновляем счетчики передачи
            transfer.transferred_requests += 1
            
            # Создаем запись аудита для заявки
            audit = AuditLog(
                user_id=transfer.outgoing_executor_id,
                telegram_user_id=None,
                action="REQUEST_TRANSFERRED",
                details={
                    "request_id": request_id,
                    "from_executor": old_executor_id,
                    "to_executor": transfer.incoming_executor_id,
                    "transfer_notes": transfer_notes,
                    "outgoing_shift_id": transfer.outgoing_shift_id,
                    "incoming_shift_id": transfer.incoming_shift_id
                }
            )
            self.db.add(audit)
            
            self.db.commit()
            logger.info(f"Заявка {request_id} передана исполнителю {transfer.incoming_executor_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка передачи заявки {request_id}: {e}")
            self.db.rollback()
            transfer.failed_requests += 1
            return False
    
    def complete_transfer(self, transfer: ShiftTransfer, executor_id: int, completion_notes: Optional[str] = None) -> bool:
        """
        Завершает передачу заявок между сменами
        
        Args:
            transfer: Объект передачи
            executor_id: ID исполнителя, завершающего передачу
            completion_notes: Комментарии о завершении
        
        Returns:
            bool: True если передача завершена успешно
        """
        try:
            if transfer.status != TransferStatus.IN_PROGRESS:
                logger.error(f"Неверный статус для завершения передачи: {transfer.status}")
                return False
            
            # Может завершить как исходящий, так и входящий исполнитель
            if executor_id not in [transfer.outgoing_executor_id, transfer.incoming_executor_id]:
                logger.error("Завершить передачу могут только участвующие исполнители")
                return False
            
            # Проверяем, что все заявки обработаны
            pending_requests = transfer.total_requests - transfer.transferred_requests - transfer.failed_requests
            if pending_requests > 0:
                logger.warning(f"Остались необработанные заявки: {pending_requests}")
                # Можем разрешить завершение с предупреждением
            
            # Завершаем передачу
            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = datetime.now()
            if completion_notes:
                transfer.transfer_notes = completion_notes
            
            # Обновляем статусы смен
            outgoing_shift = self.db.query(Shift).filter(Shift.id == transfer.outgoing_shift_id).first()
            incoming_shift = self.db.query(Shift).filter(Shift.id == transfer.incoming_shift_id).first()
            
            if outgoing_shift:
                outgoing_shift.status = "completed"
                outgoing_shift.actual_end_time = datetime.now()
                
                # Обновляем статистику исходящей смены
                outgoing_shift.completed_requests = transfer.transferred_requests + transfer.failed_requests
            
            if incoming_shift:
                incoming_shift.status = "active"
                incoming_shift.actual_start_time = datetime.now()
            
            # Создаем финальный аудит
            self._create_transfer_audit(transfer, executor_id, "completed")
            
            # Уведомляем о завершении
            self._notify_transfer_completed(transfer)
            
            self.db.commit()
            logger.info(f"Передача завершена: {transfer.transferred_requests}/{transfer.total_requests} заявок")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка завершения передачи: {e}")
            self.db.rollback()
            return False
    
    def cancel_transfer(self, transfer: ShiftTransfer, executor_id: int, reason: str) -> bool:
        """
        Отменяет передачу заявок
        
        Args:
            transfer: Объект передачи
            executor_id: ID исполнителя, отменяющего передачу
            reason: Причина отмены
        
        Returns:
            bool: True если передача отменена успешно
        """
        try:
            if transfer.status not in [TransferStatus.PENDING, TransferStatus.IN_PROGRESS]:
                logger.error(f"Нельзя отменить передачу в статусе: {transfer.status}")
                return False
            
            # Отменяем передачу
            transfer.status = TransferStatus.CANCELLED
            transfer.transfer_notes = f"Отменено: {reason}"
            
            # Возвращаем смены в исходное состояние
            outgoing_shift = self.db.query(Shift).filter(Shift.id == transfer.outgoing_shift_id).first()
            incoming_shift = self.db.query(Shift).filter(Shift.id == transfer.incoming_shift_id).first()
            
            if outgoing_shift and outgoing_shift.status == "in_transition":
                outgoing_shift.status = "active"  # Возвращаем в активное состояние
            
            if incoming_shift and incoming_shift.status != "planned":
                incoming_shift.status = "planned"  # Возвращаем в запланированное состояние
            
            # Откатываем переданные заявки
            for i in range(transfer.transferred_requests):
                # Здесь нужно найти и откатить уже переданные заявки
                # Это сложная операция, возможно стоит ограничить отмену только для PENDING статуса
                pass
            
            # Создаем аудит отмены
            self._create_transfer_audit(transfer, executor_id, "cancelled", reason)
            
            # Уведомляем об отмене
            self._notify_transfer_cancelled(transfer, reason)
            
            self.db.commit()
            logger.info(f"Передача отменена: {reason}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отмены передачи: {e}")
            self.db.rollback()
            return False
    
    # ========== АВТОМАТИЧЕСКИЕ ПРОЦЕССЫ ==========
    
    def auto_detect_required_transfers(self, time_window_minutes: int = 30) -> List[Tuple[int, int]]:
        """
        Автоматически определяет смены, которые требуют передачи заявок
        
        Args:
            time_window_minutes: Временное окно для поиска завершающихся смен
        
        Returns:
            List[Tuple[int, int]]: Список пар (исходящая_смена_id, входящая_смена_id)
        """
        try:
            now = datetime.now()
            window_start = now
            window_end = now + timedelta(minutes=time_window_minutes)
            
            # Ищем смены, которые завершаются в ближайшее время
            ending_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.status == "active",
                    Shift.planned_end_time >= window_start,
                    Shift.planned_end_time <= window_end
                )
            ).all()
            
            transfer_pairs = []
            
            for ending_shift in ending_shifts:
                # Ищем следующую смену той же специализации
                next_shift = self._find_next_shift_for_specialization(
                    ending_shift.specialization_focus,
                    ending_shift.planned_end_time
                )
                
                if next_shift:
                    transfer_pairs.append((ending_shift.id, next_shift.id))
                    logger.info(f"Обнаружена необходимость передачи: {ending_shift.id} → {next_shift.id}")
                else:
                    logger.warning(f"Не найдена следующая смена для специализации {ending_shift.specialization_focus}")
            
            return transfer_pairs
            
        except Exception as e:
            logger.error(f"Ошибка автоопределения передач: {e}")
            return []
    
    def _find_next_shift_for_specialization(
        self, 
        specialization_focus: List[str], 
        after_time: datetime
    ) -> Optional[Shift]:
        """Находит следующую смену для той же специализации"""
        try:
            # Ищем ближайшую запланированную смену с той же специализацией
            next_shift = self.db.query(Shift).filter(
                and_(
                    Shift.status == "planned",
                    Shift.planned_start_time >= after_time - timedelta(hours=1),  # Небольшое перекрытие
                    Shift.planned_start_time <= after_time + timedelta(hours=8),   # В разумных пределах
                    or_(*[
                        Shift.specialization_focus.contains([spec]) 
                        for spec in specialization_focus
                    ])
                )
            ).order_by(Shift.planned_start_time).first()
            
            return next_shift
            
        except Exception as e:
            logger.error(f"Ошибка поиска следующей смены: {e}")
            return None
    
    def auto_initiate_transfers(self) -> List[ShiftTransfer]:
        """Автоматически инициирует передачи для обнаруженных смен"""
        try:
            transfer_pairs = self.auto_detect_required_transfers()
            initiated_transfers = []
            
            for outgoing_id, incoming_id in transfer_pairs:
                transfer = self.initiate_shift_transfer(
                    outgoing_id, 
                    incoming_id, 
                    initiated_by=0  # Системная инициация
                )
                
                if transfer:
                    initiated_transfers.append(transfer)
            
            logger.info(f"Автоматически инициировано {len(initiated_transfers)} передач")
            return initiated_transfers
            
        except Exception as e:
            logger.error(f"Ошибка автоинициации передач: {e}")
            return []
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _create_transfer_audit(self, transfer: ShiftTransfer, user_id: int, action: str, details: str = None):
        """Создает запись аудита для передачи"""
        try:
            audit = AuditLog(
                user_id=user_id,
                telegram_user_id=None,
                action=f"SHIFT_TRANSFER_{action.upper()}",
                details={
                    "outgoing_shift_id": transfer.outgoing_shift_id,
                    "incoming_shift_id": transfer.incoming_shift_id,
                    "outgoing_executor_id": transfer.outgoing_executor_id,
                    "incoming_executor_id": transfer.incoming_executor_id,
                    "total_requests": transfer.total_requests,
                    "transferred_requests": transfer.transferred_requests,
                    "failed_requests": transfer.failed_requests,
                    "status": transfer.status.value,
                    "details": details
                }
            )
            self.db.add(audit)
            
        except Exception as e:
            logger.error(f"Ошибка создания аудита передачи: {e}")
    
    def _notify_transfer_initiated(self, transfer: ShiftTransfer):
        """Уведомляет участников о начале передачи"""
        try:
            # Уведомляем исходящего исполнителя
            self.notification_service.notify_user(
                transfer.outgoing_executor_id,
                "Инициирована передача смены",
                f"Передача {transfer.total_requests} заявок следующей смене. Начните процесс передачи в удобное время."
            )
            
            # Уведомляем входящего исполнителя
            self.notification_service.notify_user(
                transfer.incoming_executor_id,
                "Вам будут переданы заявки",
                f"От предыдущей смены будет передано {transfer.total_requests} активных заявок. Будьте готовы к приему."
            )
            
        except Exception as e:
            logger.error(f"Ошибка уведомлений о передаче: {e}")
    
    def _notify_transfer_started(self, transfer: ShiftTransfer):
        """Уведомляет о начале процесса передачи"""
        try:
            self.notification_service.notify_user(
                transfer.incoming_executor_id,
                "Начался процесс передачи смены",
                f"Предыдущая смена начала передачу {transfer.total_requests} заявок. Подготовьтесь к их приему."
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления о начале передачи: {e}")
    
    def _notify_transfer_completed(self, transfer: ShiftTransfer):
        """Уведомляет о завершении передачи"""
        try:
            success_rate = (transfer.transferred_requests / transfer.total_requests * 100) if transfer.total_requests > 0 else 100
            
            message = f"Передача смены завершена. Передано: {transfer.transferred_requests}/{transfer.total_requests} заявок ({success_rate:.1f}%)"
            if transfer.failed_requests > 0:
                message += f". Ошибок: {transfer.failed_requests}"
            
            # Уведомляем обоих исполнителей
            self.notification_service.notify_user(transfer.outgoing_executor_id, "Передача завершена", message)
            self.notification_service.notify_user(transfer.incoming_executor_id, "Смена принята", message)
            
        except Exception as e:
            logger.error(f"Ошибка уведомления о завершении: {e}")
    
    def _notify_transfer_cancelled(self, transfer: ShiftTransfer, reason: str):
        """Уведомляет об отмене передачи"""
        try:
            message = f"Передача смены отменена. Причина: {reason}"
            
            self.notification_service.notify_user(transfer.outgoing_executor_id, "Передача отменена", message)
            self.notification_service.notify_user(transfer.incoming_executor_id, "Передача отменена", message)
            
        except Exception as e:
            logger.error(f"Ошибка уведомления об отмене: {e}")
    
    # ========== СТАТИСТИКА И АНАЛИТИКА ==========
    
    def get_transfer_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Возвращает статистику передач за указанный период"""
        try:
            # Здесь будет запрос к таблице передач, когда она будет создана
            # Пока возвращаем базовую статистику
            return {
                "total_transfers": 0,
                "successful_transfers": 0,
                "failed_transfers": 0,
                "average_transfer_time": 0,
                "total_requests_transferred": 0,
                "transfer_success_rate": 0
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики передач: {e}")
            return {}
    
    def get_active_transfers(self) -> List[ShiftTransfer]:
        """Возвращает список активных передач"""
        try:
            # Здесь будет запрос к БД для получения активных передач
            # Пока возвращаем пустой список
            return []
            
        except Exception as e:
            logger.error(f"Ошибка получения активных передач: {e}")
            return []