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
    # Поля, которым мало быть строкой — они должны нести текст. Проверки типа
    # недостаточно там, где значение читает человек: "   " формально str, но
    # исполнитель увидит пустоту. Держим правило рядом со схемой, а не в
    # plan_transition — иначе оно потеряется при добавлении новых действий.
    non_empty: frozenset[str] = frozenset()

    def validate(self, action: Action, payload: Mapping[str, object]) -> None:
        for key, typ in self.required.items():
            if key not in payload:
                raise PayloadInvalid(f"{action.value}: missing required '{key}'")
            if not isinstance(payload[key], typ):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {typ.__name__}")
        for key in self.non_empty:
            value = payload.get(key)
            if isinstance(value, str) and not value.strip():
                raise PayloadInvalid(f"{action.value}: '{key}' must not be blank")
        allowed = set(self.required) | set(self.optional)
        for key in payload:
            if key not in allowed:
                raise PayloadInvalid(f"{action.value}: unexpected field '{key}'")
            if key in self.optional and payload[key] is not None \
                    and not isinstance(payload[key], self.optional[key]):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {self.optional[key].__name__}")


PAYLOAD_SCHEMAS: Mapping[Action, PayloadSchema] = {
    # Инвариант «В работе ⟺ есть исполнитель»: оба действия ведут в «В работе»,
    # поэтому исполнитель ОБЯЗАТЕЛЕН. Раньше оба поля были опциональны, и это
    # давало два способа завести ничью заявку: `group` (заявка уезжала в
    # «В работе» на группу, без человека) и пустой payload («менеджер взял
    # заявку, исполнителя выберет потом»). Группа переехала в ASSIGN_GROUP,
    # которое статус не меняет; `group` здесь теперь — unexpected field.
    Action.SYSTEM_DISPATCH_ASSIGN: PayloadSchema(
        required={"executor_id": int}),
    Action.MANAGER_ASSIGN: PayloadSchema(
        required={"executor_id": int}),
    # `group` проверяется по канону в `plan_transition`, а не только на непустоту:
    # значение уходит в предикат доступа к заявке и в гвард взятия, поэтому
    # произвольная строка здесь — это запись мусора в поле авторизации.
    Action.ASSIGN_GROUP: PayloadSchema(
        required={"group": str}, non_empty=frozenset({"group"})),
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
    # reason ОБЯЗАТЕЛЕН и непуст: возврат без объяснения бесполезен исполнителю
    # — он не знает, что переделывать. Раньше причина была опциональной, бот слал
    # пустой payload, а текст оседал только в audit_logs. Одна проверка в ядре
    # закрывает все три точки входа (бот, API, request_service).
    Action.MANAGER_RETURN_TO_WORK: PayloadSchema(
        required={"reason": str}, non_empty=frozenset({"reason"})),
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
    # Категория проверяется по канону в `plan_transition` (как `group` у
    # ASSIGN_GROUP): значение уходит в диспетч и видимость исполнителям.
    Action.MANAGER_CHANGE_CATEGORY: PayloadSchema(
        required={"category": str}, non_empty=frozenset({"category"})),
}
