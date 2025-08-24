"""
Сервис верификации пользователей

Предоставляет функции для:
- Управления процессом верификации пользователей
- Запроса дополнительной информации
- Проверки документов
- Управления правами доступа
"""

import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import (
    UserDocument, UserVerification, AccessRights,
    DocumentType, VerificationStatus, AccessLevel
)
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


class UserVerificationService:
    """Сервис верификации пользователей"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ═══ УПРАВЛЕНИЕ ВЕРИФИКАЦИЕЙ ═══
    
    def create_verification_request(self, user_id: int, admin_id: int, requested_info: Dict[str, Any]) -> UserVerification:
        """
        Создать запрос на верификацию пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            requested_info: Запрашиваемая информация
            
        Returns:
            UserVerification объект
        """
        try:
            # Проверяем, есть ли уже активная верификация
            existing_verification = self.db.query(UserVerification).filter(
                and_(
                    UserVerification.user_id == user_id,
                    UserVerification.status.in_([VerificationStatus.PENDING, VerificationStatus.REQUESTED])
                )
            ).first()
            
            if existing_verification:
                # Обновляем существующую верификацию
                existing_verification.status = VerificationStatus.REQUESTED
                existing_verification.requested_info = requested_info
                existing_verification.requested_at = datetime.now()
                existing_verification.requested_by = admin_id
                self.db.commit()
                return existing_verification
            
            # Создаем новую верификацию
            verification = UserVerification(
                user_id=user_id,
                status=VerificationStatus.REQUESTED,
                requested_info=requested_info,
                requested_at=datetime.now(),
                requested_by=admin_id
            )
            
            self.db.add(verification)
            self.db.commit()
            self.db.refresh(verification)
            
            logger.info(f"Создан запрос верификации для пользователя {user_id}")
            return verification
            
        except Exception as e:
            logger.error(f"Ошибка создания запроса верификации: {e}")
            self.db.rollback()
            raise
    
    def approve_verification(self, user_id: int, admin_id: int, notes: str = None) -> bool:
        """
        Одобрить верификацию пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            notes: Комментарии администратора
            
        Returns:
            True если успешно
        """
        try:
            # Обновляем статус пользователя
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            user.verification_status = "verified"
            user.verification_notes = notes
            user.verification_date = datetime.now()
            user.verified_by = admin_id
            
            # Обновляем статус верификации
            verification = self.db.query(UserVerification).filter(
                and_(
                    UserVerification.user_id == user_id,
                    UserVerification.status.in_([VerificationStatus.PENDING, VerificationStatus.REQUESTED])
                )
            ).first()
            
            if verification:
                verification.status = VerificationStatus.APPROVED
                verification.verified_by = admin_id
                verification.verified_at = datetime.now()
                verification.admin_notes = notes
            
            self.db.commit()
            logger.info(f"Верификация пользователя {user_id} одобрена администратором {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка одобрения верификации: {e}")
            self.db.rollback()
            return False
    
    def reject_verification(self, user_id: int, admin_id: int, notes: str) -> bool:
        """
        Отклонить верификацию пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            notes: Причина отклонения
            
        Returns:
            True если успешно
        """
        try:
            # Обновляем статус пользователя
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            user.verification_status = "rejected"
            user.verification_notes = notes
            user.verification_date = datetime.now()
            user.verified_by = admin_id
            
            # Обновляем статус верификации
            verification = self.db.query(UserVerification).filter(
                and_(
                    UserVerification.user_id == user_id,
                    UserVerification.status.in_([VerificationStatus.PENDING, VerificationStatus.REQUESTED])
                )
            ).first()
            
            if verification:
                verification.status = VerificationStatus.REJECTED
                verification.verified_by = admin_id
                verification.verified_at = datetime.now()
                verification.admin_notes = notes
            
            self.db.commit()
            logger.info(f"Верификация пользователя {user_id} отклонена администратором {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отклонения верификации: {e}")
            self.db.rollback()
            return False
    
    # ═══ УПРАВЛЕНИЕ ДОКУМЕНТАМИ ═══
    
    def add_document(self, user_id: int, document_type: DocumentType, file_id: str, 
                    file_name: str = None, file_size: int = None) -> UserDocument:
        """
        Добавить документ пользователя
        
        Args:
            user_id: ID пользователя
            document_type: Тип документа
            file_id: Telegram file_id
            file_name: Имя файла
            file_size: Размер файла
            
        Returns:
            UserDocument объект
        """
        try:
            document = UserDocument(
                user_id=user_id,
                document_type=document_type,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size
            )
            
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            
            logger.info(f"Добавлен документ {document_type.value} для пользователя {user_id}")
            return document
            
        except Exception as e:
            logger.error(f"Ошибка добавления документа: {e}")
            self.db.rollback()
            raise
    
    def verify_document(self, document_id: int, admin_id: int, status: VerificationStatus, 
                       notes: str = None) -> bool:
        """
        Проверить документ пользователя
        
        Args:
            document_id: ID документа
            admin_id: ID администратора
            status: Статус проверки
            notes: Комментарии
            
        Returns:
            True если успешно
        """
        try:
            document = self.db.query(UserDocument).filter(UserDocument.id == document_id).first()
            if not document:
                return False
            
            document.verification_status = status
            document.verification_notes = notes
            document.verified_by = admin_id
            document.verified_at = datetime.now()
            
            self.db.commit()
            logger.info(f"Документ {document_id} проверен администратором {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки документа: {e}")
            self.db.rollback()
            return False
    
    def get_user_documents(self, user_id: int) -> List[UserDocument]:
        """
        Получить документы пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список документов
        """
        try:
            documents = self.db.query(UserDocument).filter(
                UserDocument.user_id == user_id
            ).order_by(UserDocument.created_at.desc()).all()
            
            return documents
            
        except Exception as e:
            logger.error(f"Ошибка получения документов пользователя: {e}")
            return []
    
    # ═══ УПРАВЛЕНИЕ ПРАВАМИ ДОСТУПА ═══
    
    def grant_access_rights(self, user_id: int, admin_id: int, access_level: AccessLevel,
                          apartment_number: str = None, house_number: str = None, 
                          yard_name: str = None, notes: str = None) -> AccessRights:
        """
        Предоставить права доступа пользователю
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            access_level: Уровень доступа
            apartment_number: Номер квартиры (для APARTMENT)
            house_number: Номер дома (для HOUSE)
            yard_name: Название двора (для YARD)
            notes: Комментарии
            
        Returns:
            AccessRights объект
        """
        try:
            # Проверяем ограничения для квартиры (максимум 2 заявителя)
            if access_level == AccessLevel.APARTMENT and apartment_number:
                existing_users = self.db.query(AccessRights).filter(
                    and_(
                        AccessRights.access_level == AccessLevel.APARTMENT,
                        AccessRights.apartment_number == apartment_number,
                        AccessRights.is_active == True
                    )
                ).count()
                
                if existing_users >= 2:
                    raise ValueError(f"Квартира {apartment_number} уже имеет максимальное количество заявителей (2)")
            
            # Создаем права доступа
            access_rights = AccessRights(
                user_id=user_id,
                access_level=access_level,
                apartment_number=apartment_number,
                house_number=house_number,
                yard_name=yard_name,
                granted_by=admin_id,
                notes=notes
            )
            
            self.db.add(access_rights)
            self.db.commit()
            self.db.refresh(access_rights)
            
            logger.info(f"Предоставлены права доступа {access_level.value} пользователю {user_id}")
            return access_rights
            
        except Exception as e:
            logger.error(f"Ошибка предоставления прав доступа: {e}")
            self.db.rollback()
            raise
    
    def revoke_access_rights(self, rights_id: int, admin_id: int, notes: str = None) -> bool:
        """
        Отозвать права доступа
        
        Args:
            rights_id: ID прав доступа
            admin_id: ID администратора
            notes: Комментарии
            
        Returns:
            True если успешно
        """
        try:
            rights = self.db.query(AccessRights).filter(AccessRights.id == rights_id).first()
            if not rights:
                return False
            
            rights.is_active = False
            rights.notes = notes if notes else rights.notes
            
            self.db.commit()
            logger.info(f"Отозваны права доступа {rights_id} администратором {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отзыва прав доступа: {e}")
            self.db.rollback()
            return False
    
    def get_user_access_rights(self, user_id: int) -> List[AccessRights]:
        """
        Получить права доступа пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список прав доступа
        """
        try:
            rights = self.db.query(AccessRights).filter(
                and_(
                    AccessRights.user_id == user_id,
                    AccessRights.is_active == True
                )
            ).order_by(AccessRights.created_at.desc()).all()
            
            return rights
            
        except Exception as e:
            logger.error(f"Ошибка получения прав доступа пользователя: {e}")
            return []
    
    # ═══ ПОЛУЧЕНИЕ СТАТИСТИКИ ═══
    
    def get_verification_stats(self) -> Dict[str, int]:
        """
        Получить статистику верификации
        
        Returns:
            Словарь со статистикой
        """
        try:
            stats = {
                'pending': self.db.query(User).filter(User.verification_status == 'pending').count(),
                'verified': self.db.query(User).filter(User.verification_status == 'verified').count(),
                'rejected': self.db.query(User).filter(User.verification_status == 'rejected').count(),
                'total_documents': self.db.query(UserDocument).count(),
                'pending_documents': self.db.query(UserDocument).filter(
                    UserDocument.verification_status == VerificationStatus.PENDING
                ).count()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики верификации: {e}")
            return {
                'pending': 0,
                'verified': 0,
                'rejected': 0,
                'total_documents': 0,
                'pending_documents': 0
            }

    def request_additional_documents(self, user_id: int, admin_id: int, request_text: str) -> bool:
        """
        Запросить дополнительные документы у пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            request_text: Текст запроса
            
        Returns:
            True если успешно
        """
        try:
            # Создаем запрос на верификацию с запросом документов
            requested_info = {
                'type': 'additional_documents',
                'request_text': request_text,
                'requested_at': datetime.now().isoformat()
            }
            
            verification = self.create_verification_request(user_id, admin_id, requested_info)
            
            # Обновляем статус пользователя на "запрошена информация"
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user.verification_status = 'requested'
                self.db.commit()
            
            logger.info(f"Запрошены дополнительные документы для пользователя {user_id} от администратора {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запроса дополнительных документов: {e}")
            self.db.rollback()
            return False

    def request_specific_document(self, user_id: int, admin_id: int, document_type: str, request_text: str) -> bool:
        """
        Запросить конкретный тип документа у пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            document_type: Тип документа (passport, property_deed, etc.)
            request_text: Текст запроса
            
        Returns:
            True если успешно
        """
        try:
            # Создаем запрос на верификацию с запросом конкретного документа
            requested_info = {
                'type': 'specific_document',
                'document_type': document_type,
                'request_text': request_text,
                'requested_at': datetime.now().isoformat()
            }
            
            verification = self.create_verification_request(user_id, admin_id, requested_info)
            
            # Обновляем статус пользователя на "запрошена информация"
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user.verification_status = 'requested'
                self.db.commit()
            
            logger.info(f"Запрошен документ типа {document_type} для пользователя {user_id} от администратора {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запроса конкретного документа: {e}")
            self.db.rollback()
            return False

    def request_multiple_documents(self, user_id: int, admin_id: int, document_types: list, request_text: str) -> bool:
        """
        Запросить несколько типов документов у пользователя
        
        Args:
            user_id: ID пользователя
            admin_id: ID администратора
            document_types: Список типов документов
            request_text: Текст запроса
            
        Returns:
            True если успешно
        """
        try:
            # Создаем запрос на верификацию с запросом множественных документов
            requested_info = {
                'type': 'multiple_documents',
                'document_types': document_types,
                'request_text': request_text,
                'requested_at': datetime.now().isoformat()
            }
            
            verification = self.create_verification_request(user_id, admin_id, requested_info)
            
            # Обновляем статус пользователя на "запрошена информация"
            user = self.db.query(User).filter(User.id == user_id).first()
            if user:
                user.verification_status = 'requested'
                self.db.commit()
            
            logger.info(f"Запрошены документы типов {document_types} для пользователя {user_id} от администратора {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка запроса множественных документов: {e}")
            self.db.rollback()
            return False

    # ═══ УПРАВЛЕНИЕ ДОКУМЕНТАМИ В ОНБОРДИНГЕ ═══
    
    def save_user_document(self, user_id: int, document_type: DocumentType, file_id: str, 
                          file_name: str = None, file_size: int = None) -> UserDocument:
        """
        Сохранить документ пользователя в базе данных
        
        Args:
            user_id: ID пользователя
            document_type: Тип документа
            file_id: Telegram file_id
            file_name: Имя файла
            file_size: Размер файла
            
        Returns:
            UserDocument объект
        """
        try:
            # Создаем новый документ
            document = UserDocument(
                user_id=user_id,
                document_type=document_type,
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                verification_status=VerificationStatus.PENDING
            )
            
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            
            logger.info(f"Сохранен документ типа {document_type.value} для пользователя {user_id}")
            return document
            
        except Exception as e:
            logger.error(f"Ошибка сохранения документа: {e}")
            self.db.rollback()
            raise
    
    def get_user_documents(self, user_id: int) -> List[UserDocument]:
        """
        Получить все документы пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список документов пользователя
        """
        try:
            documents = self.db.query(UserDocument).filter(
                UserDocument.user_id == user_id
            ).order_by(UserDocument.created_at.desc()).all()
            
            return documents
            
        except Exception as e:
            logger.error(f"Ошибка получения документов пользователя {user_id}: {e}")
            return []
    
    def get_user_documents_by_type(self, user_id: int, document_type: DocumentType) -> List[UserDocument]:
        """
        Получить документы пользователя определенного типа
        
        Args:
            user_id: ID пользователя
            document_type: Тип документа
            
        Returns:
            Список документов указанного типа
        """
        try:
            documents = self.db.query(UserDocument).filter(
                and_(
                    UserDocument.user_id == user_id,
                    UserDocument.document_type == document_type
                )
            ).order_by(UserDocument.created_at.desc()).all()
            
            return documents
            
        except Exception as e:
            logger.error(f"Ошибка получения документов типа {document_type.value} для пользователя {user_id}: {e}")
            return []
    
    def delete_user_document(self, document_id: int, user_id: int) -> bool:
        """
        Удалить документ пользователя
        
        Args:
            document_id: ID документа
            user_id: ID пользователя (для проверки прав)
            
        Returns:
            True если успешно
        """
        try:
            document = self.db.query(UserDocument).filter(
                and_(
                    UserDocument.id == document_id,
                    UserDocument.user_id == user_id
                )
            ).first()
            
            if document:
                self.db.delete(document)
                self.db.commit()
                logger.info(f"Удален документ {document_id} пользователя {user_id}")
                return True
            else:
                logger.warning(f"Документ {document_id} не найден для пользователя {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка удаления документа {document_id}: {e}")
            self.db.rollback()
            return False
    
    def get_user_documents_summary(self, user_id: int) -> Dict[str, Any]:
        """
        Получить сводку документов пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Словарь со сводкой документов
        """
        try:
            documents = self.get_user_documents(user_id)
            
            summary = {
                'total_documents': len(documents),
                'documents_by_type': {},
                'pending_documents': 0,
                'approved_documents': 0,
                'rejected_documents': 0
            }
            
            for doc in documents:
                # Подсчет по типам
                doc_type = doc.document_type.value
                if doc_type not in summary['documents_by_type']:
                    summary['documents_by_type'][doc_type] = 0
                summary['documents_by_type'][doc_type] += 1
                
                # Подсчет по статусам
                if doc.verification_status == VerificationStatus.PENDING:
                    summary['pending_documents'] += 1
                elif doc.verification_status == VerificationStatus.APPROVED:
                    summary['approved_documents'] += 1
                elif doc.verification_status == VerificationStatus.REJECTED:
                    summary['rejected_documents'] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"Ошибка получения сводки документов для пользователя {user_id}: {e}")
            return {
                'total_documents': 0,
                'documents_by_type': {},
                'pending_documents': 0,
                'approved_documents': 0,
                'rejected_documents': 0
            }
    
    def validate_document_file(self, file_id: str, file_name: str = None, file_size: int = None) -> tuple[bool, str]:
        """
        Валидировать загружаемый файл документа
        
        Args:
            file_id: Telegram file_id
            file_name: Имя файла
            file_size: Размер файла
            
        Returns:
            (is_valid, error_message)
        """
        try:
            # Проверяем наличие file_id
            if not file_id:
                return False, "Отсутствует идентификатор файла"
            
            # Проверяем размер файла (максимум 50MB для Telegram)
            if file_size and file_size > 50 * 1024 * 1024:
                return False, "Размер файла превышает 50MB"
            
            # Проверяем расширение файла
            if file_name:
                allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.doc', '.docx']
                file_extension = file_name.lower()
                if not any(file_extension.endswith(ext) for ext in allowed_extensions):
                    return False, f"Неподдерживаемый тип файла. Разрешены: {', '.join(allowed_extensions)}"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Ошибка валидации файла: {e}")
            return False, "Ошибка валидации файла"
