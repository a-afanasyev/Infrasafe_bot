"""
Type-safe CallbackData factories for aiogram 3.x.

Usage in keyboards:
    button = InlineKeyboardButton(
        text="Category",
        callback_data=CategoryCB(id="electric").pack()
    )

Usage in handlers:
    @router.callback_query(CategoryCB.filter())
    async def handle_category(cb: CallbackQuery, callback_data: CategoryCB):
        category_id = callback_data.id
"""
from aiogram.filters.callback_data import CallbackData


class CategoryCB(CallbackData, prefix="cat"):
    """Request category selection."""
    id: str


class UrgencyCB(CallbackData, prefix="urg"):
    """Request urgency selection."""
    level: str


class PageCB(CallbackData, prefix="pg"):
    """Pagination callback."""
    page: int
    context: str = ""  # e.g. "my_requests", "all_requests"


class RequestActionCB(CallbackData, prefix="req"):
    """Action on a specific request."""
    action: str  # view, edit, assign, status, comment, report
    id: int  # request ID or request_number


class RoleSwitchCB(CallbackData, prefix="role"):
    """Role switching."""
    target: str  # applicant, executor, manager


class StatusFilterCB(CallbackData, prefix="sf"):
    """Request status filter selection."""
    status: str


class RatingCB(CallbackData, prefix="rate"):
    """Rating callback."""
    score: int
    request_id: int = 0


class ShiftActionCB(CallbackData, prefix="shft"):
    """Shift actions."""
    action: str  # details, start, end, transfer
    id: int = 0


class AddressCB(CallbackData, prefix="addr"):
    """Address selection callback."""
    entity: str  # yard, building, apartment
    action: str  # select, edit, delete
    id: int


class UserActionCB(CallbackData, prefix="usr"):
    """User management actions."""
    action: str  # approve, block, unblock, delete, role
    id: int
