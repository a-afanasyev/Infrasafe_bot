"""InfraSafe alert → UK request field mappings (FIX-007 Phase 2).

Согласовано в контракте FIX-007 (разделы O1, P1). UK владеет таксономией
категорий — InfraSafe шлёт только `type` и `severity`.
"""

from uk_management_bot.utils.constants import URGENCY_VALUES

# alert.type → UK request category. Неизвестный type → DEFAULT_CATEGORY.
TYPE_TO_CATEGORY = {
    # Активные типы (InfraSafe alert_rules)
    "TRANSFORMER_OVERLOAD": "Электрика",
    "TRANSFORMER_CRITICAL_OVERLOAD": "Электрика",
    "VOLTAGE_ANOMALY": "Электрика",
    "LEAK_DETECTED": "Сантехника",
    "HEATING_FAILURE": "Отопление",
    # Зарезервированные будущие типы (контракт O1.4 / P1)
    "POWER_FAILURE": "Электрика",
    "OVERHEATING": "Электрика",
    "TEMPERATURE_ANOMALY": "Отопление",
    "LOW_PRESSURE": "Сантехника",
    "WATER_LEAK": "Сантехника",
    "COMMUNICATION_LOST": "Безопасность",
}
DEFAULT_CATEGORY = "Другое"

# alert.severity → UK request urgency (канон-ключи, TASK 17). InfraSafe шлёт WARNING / CRITICAL.
SEVERITY_TO_URGENCY = {
    "WARNING": "low",
    "CRITICAL": "high",
}
DEFAULT_URGENCY = "low"

# Sprint 10 / INT-120 — канонический набор urgency-ключей. Валидация
# `uk_urgency_override` теперь идёт через normalize_urgency (ключ|рус→ключ)
# в inbound_alert; этот набор оставлен как канон-референс/совместимость.
URGENCY_LADDER = frozenset(URGENCY_VALUES)

# Sprint 10 / INT-120 — `event=alert.engineer_required` (chain hit
# `max_reopens_per_24h`). Per InfraSafe Sprint 10 spec §2.4 these are fixed:
# дальнейшая automatic re-escalation для chain'а не делается, route на отдельную
# инженерную очередь. UK игнорирует `uk_urgency_override`/`severity` для этого
# event-type — они нерелевантны при принудительном route'е.
ENGINEER_REQUIRED_CATEGORY = "Инженерный разбор"
ENGINEER_REQUIRED_URGENCY = "critical"  # канон-ключ (TASK 17)
