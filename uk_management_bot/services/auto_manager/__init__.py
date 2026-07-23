"""Сервис-слой «автоматического менеджера» (авто-назначение заявок).

Модули: `config.py` (валидация + load/save singleton-конфига, sync и async),
`rule_engine.py` (`select_executor` — выбор дежурного по правилу). Импортировать
напрямую: `from uk_management_bot.services.auto_manager.config import ...`.
"""
