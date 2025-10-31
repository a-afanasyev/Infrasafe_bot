#!/usr/bin/env python3
"""
Batch Translation Script - TASK 17 Phase 2
Translates all [TRANSLATE] placeholders in uz.json using Google Translate API
"""

import json
import argparse
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import logging

# Try to import googletrans, fallback to alternative if not available
try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("⚠️  googletrans not installed. Install with: pip install googletrans==4.0.0-rc1")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def flatten_dict(d: Dict[str, Any], parent_key: str = '', separator: str = '.') -> Dict[str, str]:
    """
    Flatten nested dictionary to dot notation

    Example:
        {'auth': {'pending': 'Text'}} → {'auth.pending': 'Text'}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{separator}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, separator).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(flat_dict: Dict[str, str], separator: str = '.') -> Dict[str, Any]:
    """
    Unflatten dot notation dictionary to nested structure

    Example:
        {'auth.pending': 'Text'} → {'auth': {'pending': 'Text'}}
    """
    result = {}
    for key, value in flat_dict.items():
        parts = key.split(separator)
        d = result
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
    return result


def find_translate_markers(uz_locale: Dict[str, Any], ru_locale: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Find all keys with [TRANSLATE] markers and their corresponding RU text

    Returns:
        List of (key, ru_text) tuples
    """
    uz_flat = flatten_dict(uz_locale)
    ru_flat = flatten_dict(ru_locale)

    to_translate = []
    for key, value in uz_flat.items():
        if isinstance(value, str) and value == "[TRANSLATE]":
            # Get Russian text from ru.json
            ru_text = ru_flat.get(key)
            if ru_text:
                to_translate.append((key, ru_text))
            else:
                logger.warning(f"No RU text found for key: {key}")

    return to_translate


def batch_translate_google(texts: List[str], src: str = 'ru', dest: str = 'uz') -> List[str]:
    """
    Translate a batch of texts using Google Translate

    Args:
        texts: List of texts to translate
        src: Source language code
        dest: Destination language code

    Returns:
        List of translated texts
    """
    if not TRANSLATOR_AVAILABLE:
        logger.error("Google Translator not available")
        return [f"[ERROR: Translator not available]" for _ in texts]

    translator = Translator()
    translations = []

    for text in texts:
        try:
            result = translator.translate(text, src=src, dest=dest)
            translations.append(result.text)
            logger.info(f"✅ Translated: {text[:50]}... → {result.text[:50]}...")

            # Rate limiting to avoid being blocked
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"❌ Translation failed for: {text[:50]}... - Error: {e}")
            translations.append(f"[ERROR: {text}]")
            time.sleep(2)  # Longer delay after error

    return translations


def main():
    parser = argparse.ArgumentParser(
        description="Batch translate [TRANSLATE] markers in uz.json"
    )
    parser.add_argument(
        '--ru-locale',
        default='uk_management_bot/config/locales/ru.json',
        help='Path to ru.json'
    )
    parser.add_argument(
        '--uz-locale',
        default='uk_management_bot/config/locales/uz.json',
        help='Path to uz.json'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of translations per batch'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run without updating files'
    )

    args = parser.parse_args()

    print("🌐 Batch Translation Script - TASK 17 Phase 2")
    print("=" * 80)

    if not TRANSLATOR_AVAILABLE:
        print("❌ ERROR: googletrans library not installed")
        print("   Install with: pip install googletrans==4.0.0-rc1")
        return 1

    # Load locale files
    ru_locale_path = Path(args.ru_locale)
    uz_locale_path = Path(args.uz_locale)

    if not ru_locale_path.exists():
        print(f"❌ ERROR: {ru_locale_path} not found")
        return 1

    if not uz_locale_path.exists():
        print(f"❌ ERROR: {uz_locale_path} not found")
        return 1

    print(f"📖 Loading locale files...")
    with open(ru_locale_path, 'r', encoding='utf-8') as f:
        ru_locale = json.load(f)

    with open(uz_locale_path, 'r', encoding='utf-8') as f:
        uz_locale = json.load(f)

    # Flatten locales
    ru_flat = flatten_dict(ru_locale)
    uz_flat = flatten_dict(uz_locale)

    # Find all [TRANSLATE] markers
    print(f"🔍 Finding [TRANSLATE] markers...")
    to_translate = find_translate_markers(uz_locale, ru_locale)

    if not to_translate:
        print("✅ No [TRANSLATE] markers found. All translations complete!")
        return 0

    print(f"📝 Found {len(to_translate)} strings to translate")

    if args.dry_run:
        print("\n🔍 DRY RUN - First 10 translations:")
        for key, ru_text in to_translate[:10]:
            print(f"   {key}: {ru_text[:60]}...")
        print(f"\n... and {len(to_translate) - 10} more")
        return 0

    # Translate in batches
    print(f"\n🌐 Starting batch translation (batch size: {args.batch_size})...")
    print(f"⏱️  Estimated time: {len(to_translate) * 0.5 / 60:.1f} minutes")
    print()

    translated_count = 0
    error_count = 0

    for i in range(0, len(to_translate), args.batch_size):
        batch = to_translate[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(to_translate) + args.batch_size - 1) // args.batch_size

        print(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} strings)")

        # Extract texts for translation
        keys = [key for key, _ in batch]
        texts = [ru_text for _, ru_text in batch]

        # Translate batch
        translations = batch_translate_google(texts, src='ru', dest='uz')

        # Update uz_flat
        for key, translation in zip(keys, translations):
            if not translation.startswith("[ERROR:"):
                uz_flat[key] = translation
                translated_count += 1
            else:
                uz_flat[key] = translation
                error_count += 1

        print(f"   ✅ Completed {translated_count}/{len(to_translate)}")
        print()

    # Unflatten and save
    print(f"💾 Saving translations to {uz_locale_path}...")

    # Create backup
    backup_path = uz_locale_path.with_suffix('.json.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale, f, ensure_ascii=False, indent=2)
    print(f"📦 Backup created: {backup_path}")

    # Save updated locale
    uz_locale_updated = unflatten_dict(uz_flat)
    with open(uz_locale_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale_updated, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("TRANSLATION SUMMARY")
    print("=" * 80)
    print(f"Total to translate: {len(to_translate)}")
    print(f"Successfully translated: {translated_count}")
    print(f"Errors: {error_count}")
    print(f"Success rate: {translated_count / len(to_translate) * 100:.1f}%")
    print()

    if error_count > 0:
        print("⚠️  Some translations failed. Check logs for details.")
        print("   You can re-run this script to retry failed translations.")
    else:
        print("✅ All translations completed successfully!")

    print("\n💡 Next steps:")
    print("   1. Run: python3 scripts/validate_translations.py")
    print("   2. Review critical user-facing strings manually")
    print("   3. Test bilingual flows")

    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    exit(main())
