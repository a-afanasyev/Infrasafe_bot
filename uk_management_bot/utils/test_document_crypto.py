"""Шифрование документов жителя: формат v1, AAD, отказ на чужом ключе/контексте."""
import pytest

from uk_management_bot.utils.document_crypto import (
    DocumentDecryptError,
    decrypt,
    document_aad,
    encrypt,
)

AAD = document_aad("6f1c2d3e-0000-4000-8000-000000000001", 42, "passport")


def test_roundtrip():
    key, blob = encrypt(b"%PDF-1.7 scan", AAD)
    assert decrypt(key, blob, AAD) == b"%PDF-1.7 scan"


def test_blob_is_versioned_and_opaque():
    key, blob = encrypt(b"%PDF-1.7 scan", AAD)
    assert blob.startswith(b"v1")
    assert b"%PDF" not in blob
    assert len(key) == 32


def test_same_bytes_give_different_blobs():
    """Случайные ключ и nonce: одинаковые сканы — разные файлы в Telegram (нет дедупликации)."""
    _, first = encrypt(b"same", AAD)
    _, second = encrypt(b"same", AAD)
    assert first != second


def test_wrong_key_fails():
    _, blob = encrypt(b"x", AAD)
    other_key, _ = encrypt(b"y", AAD)
    with pytest.raises(DocumentDecryptError):
        decrypt(other_key, blob, AAD)


def test_pair_moved_to_another_row_fails():
    """Пара (blob, key), перенесённая в чужую строку, не расшифровывается: AAD другой."""
    key, blob = encrypt(b"x", AAD)
    foreign = document_aad("6f1c2d3e-0000-4000-8000-000000000001", 43, "passport")
    with pytest.raises(DocumentDecryptError):
        decrypt(key, blob, foreign)


def test_unknown_version_fails():
    key, blob = encrypt(b"x", AAD)
    with pytest.raises(DocumentDecryptError):
        decrypt(key, b"v9" + blob[2:], AAD)


def test_truncated_blob_fails():
    key, _ = encrypt(b"x", AAD)
    with pytest.raises(DocumentDecryptError):
        decrypt(key, b"v1short", AAD)
