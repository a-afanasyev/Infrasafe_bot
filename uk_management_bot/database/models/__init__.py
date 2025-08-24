# Импорт всех моделей для автоматического создания таблиц

from .user import User
from .request import Request
from .shift import Shift
from .rating import Rating
from .audit import AuditLog
from .notification import Notification
from .user_verification import UserDocument, UserVerification, AccessRights, DocumentType, VerificationStatus, AccessLevel

__all__ = [
    'User',
    'Request', 
    'Shift',
    'Rating',
    'AuditLog',
    'Notification',
    'UserDocument',
    'UserVerification', 
    'AccessRights',
    'DocumentType',
    'VerificationStatus',
    'AccessLevel'
]
