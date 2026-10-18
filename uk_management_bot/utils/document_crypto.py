"""Шифрование документов жителя перед отправкой в медиа-сервис.

Ключ — на документ, хранится в строке ``UserDocument``. Удаление строки
уничтожает ключ: остаток в Telegram-канале (бот не может удалить сообщение
старше 48 ч) становится нечитаемым. Гарантия — «недоступен в live-системе»:
ключ ещё живёт в WAL/репликах/бэкапах до их ротации.

Формат blob: ``b"v1" || nonce(12) || AES-256-GCM(ciphertext+tag)``.
AAD связывает blob с конкретной строкой (uuid документа, жилец, тип) —
пара (media_id, key), перенесённая в чужую строку, не расшифруется.
"""
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = b"v1"
_NONCE_LEN = 12
_TAG_LEN = 16


class DocumentDecryptError(Exception):
    """Blob не расшифровывается этим ключом в этом контексте."""


def document_aad(document_uuid: str, user_id: int, document_type: str) -> bytes:
    return f"{document_uuid}:{user_id}:{document_type}".encode()


def encrypt(data: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """-> (key, blob). Ключ и nonce случайны: одинаковые сканы дают разные blob'ы."""
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_LEN)
    return key, _VERSION + nonce + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if not blob.startswith(_VERSION) or len(blob) < len(_VERSION) + _NONCE_LEN + _TAG_LEN:
        raise DocumentDecryptError("неизвестный формат документа")
    nonce = blob[len(_VERSION):len(_VERSION) + _NONCE_LEN]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(_VERSION) + _NONCE_LEN:], aad)
    except (InvalidTag, ValueError) as e:
        raise DocumentDecryptError("документ не расшифровывается") from e
