# Импорт всех моделей для автоматического создания таблиц

from .user import User
from .request import Request
from .shift import Shift
from .shift_template import ShiftTemplate
from .shift_schedule import ShiftSchedule
from .shift_assignment import ShiftAssignment
from .shift_transfer import ShiftTransfer
from .rating import Rating
from .audit import AuditLog
from .notification import Notification
from .user_verification import UserDocument, UserVerification, AccessRights, DocumentType, VerificationStatus, AccessLevel
from .quarterly_plan import QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict

# Импорт моделей, которые могут существовать или не существовать
try:
    from .request_comment import RequestComment
    from .request_assignment import RequestAssignment
    _request_models_available = True
except ImportError:
    _request_models_available = False

__all__ = [
    'User',
    'Request',
    'Shift',
    'ShiftTemplate',
    'ShiftSchedule',
    'ShiftAssignment',
    'ShiftTransfer',
    'Rating',
    'AuditLog',
    'Notification',
    'UserDocument',
    'UserVerification',
    'AccessRights',
    'DocumentType',
    'VerificationStatus',
    'AccessLevel',
    'QuarterlyPlan',
    'QuarterlyShiftSchedule',
    'PlanningConflict'
]

# Добавляем модели заявок, если они доступны
if _request_models_available:
    from .request_comment import RequestComment
    from .request_assignment import RequestAssignment
    __all__.extend(['RequestComment', 'RequestAssignment'])
