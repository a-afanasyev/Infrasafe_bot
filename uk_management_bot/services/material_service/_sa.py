"""SQL-хелперы UNION-журнала (см. ``reads.list_operations``).

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт. Внешних потребителей нет — используются только внутри пакета.
"""

# ===========================================================================
# SQL-хелперы
# ===========================================================================

def sa_literal(value: str):
    from sqlalchemy import literal
    return literal(value)


def sa_null_str():
    from sqlalchemy import cast, null, String
    return cast(null(), String)


def sa_false():
    from sqlalchemy import false
    return false()
