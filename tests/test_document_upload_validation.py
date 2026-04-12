"""Tests for document upload validation constants."""
from uk_management_bot.api.profile.router import ALLOWED_DOCUMENT_TYPES, ALLOWED_MIME_TYPES


class TestAllowedDocumentTypes:
    def test_contains_expected_types(self):
        for t in ("passport", "license", "insurance", "medical", "contract"):
            assert t in ALLOWED_DOCUMENT_TYPES

    def test_rejects_unknown(self):
        assert "malicious" not in ALLOWED_DOCUMENT_TYPES

    def test_is_frozenset(self):
        assert isinstance(ALLOWED_DOCUMENT_TYPES, frozenset)


class TestAllowedMimeTypes:
    def test_contains_expected_types(self):
        for t in ("application/pdf", "image/jpeg", "image/png", "image/webp"):
            assert t in ALLOWED_MIME_TYPES

    def test_rejects_executable(self):
        assert "application/x-msdownload" not in ALLOWED_MIME_TYPES

    def test_is_frozenset(self):
        assert isinstance(ALLOWED_MIME_TYPES, frozenset)
