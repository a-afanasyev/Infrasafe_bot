"""REST API модуля «Лифты» (/api/v2/elevators, Ф3a).

Пакет по образцу ``api/materials``: ``router.py`` (+ ``router_calendar.py``) —
тонкий HTTP-слой, ``service.py``/``calendar_service.py`` — API-транзакционные
обёртки над ``services/elevator_service`` (commit + отправка post-commit),
``presenters.py`` — ORM → Pydantic, ``queries.py`` — точечные выборки API-слоя,
``schemas.py`` — контракт (префикс ``Elevator*`` против коллизий в OpenAPI).
"""
