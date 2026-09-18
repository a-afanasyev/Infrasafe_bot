"""Входящие webhook'и InfraSafe → UK: схемы payload'а, маппинги, защита от replay.

AUD7-ARCH-02: раньше жило в `api/webhooks/` рядом с роутером; домен
(`services/inbound_alert.py`, клавиатуры бота) тянул HTTP-пакет. Роутер
`api/webhooks/router.py` импортирует отсюда, а не наоборот.
"""
