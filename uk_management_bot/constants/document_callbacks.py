"""callback_data кнопок документов жителя.

Здесь, а не в keyboards/: кнопки шлёт и HTTP-слой (api/residents/notify), которому
импорт UI-пакета бота запрещён гейтом A9-P2-10.
"""

#: Вход в загрузку документов (handlers/onboarding.open_document_upload, BUG-188).
UPLOAD_DOCUMENTS_CB = "docs:upload"
#: Переподача заявки на верификацию после отказа (handlers/onboarding.resubmit_verification).
RESUBMIT_CB = "verif:resubmit"
