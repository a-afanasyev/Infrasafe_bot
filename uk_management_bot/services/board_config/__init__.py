"""Конфигурация табло (board_config): дефолты, схемы хранения, загрузка/слияние.

AUD7-ARCH-02: раньше жило в `api/board_config/` — HTTP-пакете, — хотя читают его
и домен (work_reports, elevators, announcements), и роутеры. Роутер
`api/board_config/router.py` импортирует отсюда, а не наоборот.
"""
