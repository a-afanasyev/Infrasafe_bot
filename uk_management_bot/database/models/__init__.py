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
from .refresh_token import RefreshToken
from .user_verification import UserDocument, UserVerification, AccessRights, DocumentType, VerificationStatus, AccessLevel
from .quarterly_plan import QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict

# Модели справочника адресов
from .yard import Yard
from .building import Building
from .apartment import Apartment
from .user_apartment import UserApartment
from .user_yard import UserYard

# Webhook integration
from .webhook_outbox import WebhookOutbox

# Счётчик номеров заявок (PR5: gap-safe генерация YYMMDD-NNN)
from .request_number_counter import RequestNumberCounter

# Invite nonce tracking
from .invite_nonce import InviteNonce

# Resident-board public page config
from .board_config import BoardConfig

# Обратная связь (жалобы/пожелания)
from .feedback import Feedback

# Складской учёт материалов (закупки и движение матсредств)
from .material import Material, MaterialReceipt, MaterialIssue, MaterialIssueAllocation

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
    'RefreshToken',
    'UserDocument',
    'UserVerification',
    'AccessRights',
    'DocumentType',
    'VerificationStatus',
    'AccessLevel',
    'QuarterlyPlan',
    'QuarterlyShiftSchedule',
    'PlanningConflict',
    'Yard',
    'Building',
    'Apartment',
    'UserApartment',
    'UserYard',
    'WebhookOutbox',
    'InviteNonce',
    'BoardConfig',
    'Feedback',
    'RequestNumberCounter',
    'Material',
    'MaterialReceipt',
    'MaterialIssue',
    'MaterialIssueAllocation',
]

# Добавляем модели заявок, если они доступны (импортированы в try-блоке выше).
# __all__ += (не .extend) — ruff распознаёт это как пометку L41-42 экспортируемыми.
if _request_models_available:
    __all__ += ['RequestComment', 'RequestAssignment']
