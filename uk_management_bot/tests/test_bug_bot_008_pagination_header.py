"""
BUG-BOT-008: MY_REQUESTS_LIST — несогласованный шаблон заголовка пагинации.

Проверяет, что format_requests_list_header возвращает одинаковый формат
для всех фильтров (all / active / archive) и для разных страниц.
"""
import re

import pytest

from uk_management_bot.utils.request_helpers import format_requests_list_header


HEADER_PATTERN = re.compile(
    r"^📋\s+<b>[^<]+</b>\s+\(\S+\s+\d+/\d+\)\s*$",
    re.MULTILINE,
)


class TestBugBot008UnifiedPaginationHeader:
    """Все 4 заголовка должны соответствовать одному шаблону."""

    @pytest.mark.parametrize(
        "filter_,page,total",
        [
            ("all", 1, 2),
            ("all", 2, 2),
            ("active", 1, 2),
            ("archive", 1, 1),
        ],
    )
    def test_header_matches_unified_template_ru(self, filter_, page, total):
        header = format_requests_list_header(
            total_requests=10,
            current_page=page,
            total_pages=total,
            status_filter=filter_,
            role="applicant",
            language="ru",
        )
        first_line = header.strip().splitlines()[0]
        assert HEADER_PATTERN.match(first_line), (
            f"Заголовок '{first_line}' не соответствует "
            f"шаблону '📋 <b>{{filter}}</b> (стр. {{n}}/{{m}})'"
        )

    @pytest.mark.parametrize("filter_", ["all", "active", "archive"])
    def test_filter_label_is_localized_uz(self, filter_):
        header = format_requests_list_header(
            total_requests=5,
            current_page=1,
            total_pages=1,
            status_filter=filter_,
            role="applicant",
            language="uz",
        )
        first_line = header.strip().splitlines()[0]
        assert HEADER_PATTERN.match(first_line)
        # Заголовок не должен содержать «raw key» из i18n
        assert "requests." not in first_line
        assert "all_filter" not in first_line

    def test_all_four_pages_same_template(self):
        """Page1/Page2/Активные/Архив возвращают строго одну форму."""
        variants = [
            format_requests_list_header(10, 1, 2, "all", "applicant", "ru"),
            format_requests_list_header(10, 2, 2, "all", "applicant", "ru"),
            format_requests_list_header(10, 1, 2, "active", "applicant", "ru"),
            format_requests_list_header(10, 1, 1, "archive", "applicant", "ru"),
        ]
        for header in variants:
            first_line = header.strip().splitlines()[0]
            assert HEADER_PATTERN.match(first_line), header
