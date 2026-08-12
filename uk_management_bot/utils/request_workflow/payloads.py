"""Payload-схемы per action (обязательные/допустимые поля, типобезопасность).

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .types import Action, PayloadInvalid

# ---------------------------------------------------------------------------
# Payload-схемы (типобезопасность: обязательные/допустимые поля per action)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PayloadSchema:
    required: Mapping[str, type] = field(default_factory=dict)
    optional: Mapping[str, type] = field(default_factory=dict)

    def validate(self, action: Action, payload: Mapping[str, object]) -> None:
        for key, typ in self.required.items():
            if key not in payload:
                raise PayloadInvalid(f"{action.value}: missing required '{key}'")
            if not isinstance(payload[key], typ):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {typ.__name__}")
        allowed = set(self.required) | set(self.optional)
        for key in payload:
            if key not in allowed:
                raise PayloadInvalid(f"{action.value}: unexpected field '{key}'")
            if key in self.optional and payload[key] is not None \
                    and not isinstance(payload[key], self.optional[key]):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {self.optional[key].__name__}")


PAYLOAD_SCHEMAS: Mapping[Action, PayloadSchema] = {
    Action.SYSTEM_DISPATCH_ASSIGN: PayloadSchema(
        optional={"executor_id": int, "group": str}),
    Action.MANAGER_ASSIGN: PayloadSchema(
        optional={"executor_id": int, "group": str}),
    Action.EXECUTOR_PURCHASE: PayloadSchema(
        required={"requested_materials": str}),
    Action.MANAGER_PURCHASE: PayloadSchema(
        optional={"requested_materials": str}),
    # requested_materials опционален (PR2c): менеджерский возврат из закупа
    # (admin.handle_return_to_work) дописывает в список материалов разделитель
    # «--закуплено DATE--»; итог приходит готовым и пишется как SET.
    Action.MANAGER_PURCHASE_DONE: PayloadSchema(
        optional={"manager_materials_comment": str, "requested_materials": str}),
    Action.CLARIFY_REQUEST: PayloadSchema(
        required={"question": str}, optional={"notes": str}),
    Action.CLARIFY_RESOLVED: PayloadSchema(),
    Action.EXECUTOR_RESUME: PayloadSchema(),
    Action.EXECUTOR_CLAIM: PayloadSchema(),
    Action.SYSTEM_AUTO_PROMOTE: PayloadSchema(required={"executor_id": int}),
    Action.EXECUTOR_COMPLETE: PayloadSchema(
        optional={"completion_report": str, "completion_media": list}),
    Action.MANAGER_COMPLETE: PayloadSchema(
        optional={"completion_report": str, "completion_media": list}),
    Action.MANAGER_CONFIRM: PayloadSchema(
        optional={"confirmation_notes": str}),
    # reason опционален: Telegram-кнопка «вернуть в работу» причину не собирает
    # (и patch её не пишет — только audit). API при желании может прислать.
    Action.MANAGER_RETURN_TO_WORK: PayloadSchema(optional={"reason": str}),
    Action.APPLICANT_ACCEPT: PayloadSchema(required={"rating": int}),
    Action.APPLICANT_RETURN: PayloadSchema(
        required={"return_reason": str}, optional={"return_media": list}),
    Action.MANAGER_FORCE_ACCEPT: PayloadSchema(
        optional={"reason": str, "confirmation_notes": str}),
    # reason опционален: бот всегда присылает причину, но дашборд-drag в «Отменена»
    # шлёт голый статус (PR2b). reason — audit-only (в patch не пишется), поэтому
    # необязательность совпадает с прежним поведением API (прямой setattr без reason).
    Action.CANCEL: PayloadSchema(
        optional={"reason": str, "notes": str}),
}
