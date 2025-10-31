#!/usr/bin/env python3
"""
TASK 17 - Phase 2: auth.py Localization Testing Script

This script tests all 26 auth locale keys in both Russian and Uzbek languages.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from uk_management_bot.utils.helpers import get_text


def test_auth_keys():
    """Test all auth localization keys."""

    print("=" * 80)
    print("🧪 TASK 17 - auth.py Localization Test")
    print("=" * 80)
    print()

    # All 26 auth keys to test
    auth_keys = [
        "auth.login_button",
        "auth.already_authorized",
        "auth.login_success",
        "auth.login_failed",
        "auth.registration_pending",
        "auth.enter_full_name",
        "auth.full_name_invalid",
        "auth.confirm_position_prompt",
        "auth.confirm_button",
        "auth.cancel_button",
        "auth.error_try_again",
        "auth.phone_invalid",
        "auth.phone_too_short",
        "auth.confirm_data_prompt",
        "auth.registration_admin_title",
        "auth.user_field",
        "auth.phone_field",
        "auth.telegram_id_field",
        "auth.role_field",
        "auth.specialization_field",
        "auth.date_field",
        "auth.registration_complete",
        "auth.full_name_field",
        "auth.registration_submitted",
        "auth.registration_cancelled",
    ]

    errors = []
    warnings = []
    success_count = 0

    print("📋 Testing all 26 auth keys in both languages...\n")

    for key in auth_keys:
        # Test Russian
        try:
            ru_text = get_text(key, language="ru")
            if not ru_text or ru_text == key:
                errors.append(f"❌ RU: {key} - Missing or not found")
            elif ru_text.strip() == "":
                warnings.append(f"⚠️  RU: {key} - Empty string")
            else:
                success_count += 1
                # Check for Cyrillic characters
                has_cyrillic = any('\u0400' <= c <= '\u04FF' for c in ru_text)
                if not has_cyrillic and not any(c in ru_text for c in ['✅', '❌', '📋', '📝', '🔑', '👤', '📱', '🆔', '🎯', '🛠️', '📅']):
                    warnings.append(f"⚠️  RU: {key} - No Cyrillic characters found: '{ru_text}'")
        except Exception as e:
            errors.append(f"❌ RU: {key} - Error: {str(e)}")

        # Test Uzbek
        try:
            uz_text = get_text(key, language="uz")
            if not uz_text or uz_text == key:
                errors.append(f"❌ UZ: {key} - Missing or not found")
            elif uz_text.strip() == "":
                warnings.append(f"⚠️  UZ: {key} - Empty string")
            else:
                success_count += 1
                # Check that UZ is different from RU (should be translated)
                ru_text = get_text(key, language="ru")
                if uz_text == ru_text and not any(emoji in uz_text for emoji in ['✅', '❌']):
                    warnings.append(f"⚠️  UZ: {key} - Same as RU (not translated?)")
        except Exception as e:
            errors.append(f"❌ UZ: {key} - Error: {str(e)}")

    # Print results
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS")
    print("=" * 80)
    print(f"✅ Successful tests: {success_count}/{len(auth_keys) * 2}")
    print(f"❌ Errors: {len(errors)}")
    print(f"⚠️  Warnings: {len(warnings)}")
    print()

    if errors:
        print("❌ ERRORS:")
        for error in errors:
            print(f"   {error}")
        print()

    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")
        print()

    # Sample output comparison
    print("=" * 80)
    print("📝 SAMPLE OUTPUT COMPARISON")
    print("=" * 80)
    print()

    sample_keys = [
        "auth.login_button",
        "auth.enter_full_name",
        "auth.confirm_button",
        "auth.registration_complete",
        "auth.error_try_again"
    ]

    for key in sample_keys:
        ru_text = get_text(key, language="ru")
        uz_text = get_text(key, language="uz")
        print(f"🔑 {key}")
        print(f"   RU: {ru_text}")
        print(f"   UZ: {uz_text}")
        print()

    # Final verdict
    print("=" * 80)
    if len(errors) == 0:
        if len(warnings) == 0:
            print("✅ ALL TESTS PASSED! Ready for production.")
            return 0
        else:
            print("⚠️  TESTS PASSED WITH WARNINGS. Review warnings above.")
            return 0
    else:
        print("❌ TESTS FAILED! Fix errors before proceeding.")
        return 1


if __name__ == "__main__":
    exit(test_auth_keys())
