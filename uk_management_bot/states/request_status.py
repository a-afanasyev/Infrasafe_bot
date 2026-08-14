"""
FSM состояния для управления статусами заявок
Определяет состояния процесса изменения статусов заявок
"""

from aiogram.fsm.state import State, StatesGroup

class RequestStatusStates(StatesGroup):
    """Состояния для управления статусами заявок

    BUG-137: остальные стейты группы (waiting_for_status, waiting_for_comment,
    waiting_for_completion_report, waiting_for_confirmation) удалены вместе с
    мёртвым FSM-флоу — их сеттеры жили только в ретайрнутых хендлерах.
    """

    # Ввод материалов после менеджерского «Закупа» (purchase_<NNN>)
    waiting_for_materials = State()
