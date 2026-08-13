"""BUG-141 — address_service: eager f-string лог мимо гейта + лживый докстринг.

1. `user_scope.get_user_available_yards` логировал eager f-string многострочным
   вызовом (`logger.info(` + перенос строки перед `f"`) — regex-гейт
   test_pr17_address_hardening был слеп к этому случаю (расширен там же).
2. `stats.get_user_approved_apartments` — sync-метод, но докстринг называл его
   «(async обертка)».
"""
import inspect
import re

from uk_management_bot.services.address_service import AddressService
from uk_management_bot.services.address_service import stats as stats_mod
from uk_management_bot.services.address_service import user_scope as user_scope_mod


class TestBug141EagerFstringLog:
    def test_get_user_available_yards_has_no_eager_fstring_log(self):
        """Многострочный eager f-string лог убран (lazy %s-стиль)."""
        src = inspect.getsource(user_scope_mod)
        assert not re.search(
            r"logger\.(error|warning|info|exception|debug)\(\s*f[\"']", src
        ), "eager f-string лог в user_scope — BUG-141"

    def test_yards_log_kept_lazy_percent_style(self):
        """Сам лог не удалён, а переведён на lazy %s-плейсхолдеры."""
        src = inspect.getsource(user_scope_mod.UserScopeMixin.get_user_available_yards)
        assert "Найдено %s доступных дворов" in src


class TestBug141StatsDocstring:
    def test_get_user_approved_apartments_is_sync(self):
        fn = AddressService.get_user_approved_apartments
        assert not inspect.iscoroutinefunction(fn)

    def test_docstring_does_not_claim_async(self):
        """Докстринг sync-метода не должен врать про «async обертку»."""
        doc = inspect.getdoc(stats_mod.StatsMixin.get_user_approved_apartments) or ""
        assert "async обертка" not in doc, "докстринг врёт: метод sync — BUG-141"
