#!/usr/bin/env python3
"""
Locale Key Generator - TASK 17 Phase 1
Automatically generates locale keys and updates JSON locale files.

Usage:
    python scripts/generate_locale_keys.py [--input SCAN_JSON] [--mode {interactive,auto}]

Features:
    - Reads scan results from scan_hardcoded_strings.py
    - Generates unique locale keys with context-based naming
    - Interactive mode for key review/editing
    - Auto mode for batch processing
    - Updates ru.json with original strings
    - Updates uz.json with placeholder [TRANSLATE]
    - Preserves existing translations
    - Detects key conflicts
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class LocaleEntry:
    """Represents a locale key entry."""
    key: str
    ru_text: str
    uz_text: str
    source_file: str
    line_number: int
    context: str
    priority: str


class LocaleKeyGenerator:
    """Generates and manages locale keys."""

    def __init__(self, ru_locale_path: Path, uz_locale_path: Path):
        self.ru_locale_path = ru_locale_path
        self.uz_locale_path = uz_locale_path

        # Load existing locales
        self.ru_locale = self._load_locale(ru_locale_path)
        self.uz_locale = self._load_locale(uz_locale_path)

        # Track existing keys
        self.existing_keys = self._flatten_keys(self.ru_locale)

        # New entries to add
        self.new_entries: List[LocaleEntry] = []

        # Statistics
        self.stats = {
            'total_processed': 0,
            'keys_generated': 0,
            'keys_existing': 0,
            'conflicts_resolved': 0,
        }

    def _load_locale(self, path: Path) -> Dict:
        """Load locale JSON file."""
        if not path.exists():
            print(f"⚠️  Locale file not found: {path}, creating new")
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _flatten_keys(self, nested_dict: Dict, prefix: str = '') -> Dict[str, str]:
        """Flatten nested locale dictionary to dot notation."""
        flat = {}

        for key, value in nested_dict.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                flat.update(self._flatten_keys(value, full_key))
            else:
                flat[full_key] = value

        return flat

    def _unflatten_keys(self, flat_dict: Dict[str, str]) -> Dict:
        """Convert flat dict with dot notation to nested dict."""
        nested = {}

        for key, value in flat_dict.items():
            parts = key.split('.')
            current = nested

            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current[part] = value
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

        return nested

    def generate_key(self, string_value: str, context: str, file_path: str) -> str:
        """Generate a locale key from string value and context."""
        # Determine section based on file path
        section = self._determine_section(file_path)

        # Normalize and clean string
        clean = self._normalize_string(string_value)

        # Generate base key from first 2-3 words
        words = clean.split('_')[:3]
        base_key = '_'.join(words)

        # Transliterate common words
        base_key = self._transliterate(base_key)

        # Combine section + base_key
        full_key = f"{section}.{base_key}" if section else base_key

        # Ensure uniqueness
        full_key = self._ensure_unique_key(full_key, string_value)

        return full_key

    def _determine_section(self, file_path: str) -> str:
        """Determine locale section from file path."""
        path_lower = file_path.lower()

        # Handler sections
        if 'handlers/auth' in path_lower:
            return 'auth'
        elif 'handlers/onboarding' in path_lower:
            return 'onboarding'
        elif 'handlers/requests' in path_lower or 'handlers/request_' in path_lower:
            return 'requests'
        elif 'handlers/shifts' in path_lower or 'handlers/my_shifts' in path_lower:
            return 'shifts'
        elif 'handlers/admin' in path_lower:
            return 'admin'
        elif 'handlers/profile' in path_lower:
            return 'profile'
        elif 'handlers/' in path_lower:
            return 'handlers'

        # Keyboard sections
        elif 'keyboards/requests' in path_lower:
            return 'keyboards.requests'
        elif 'keyboards/shifts' in path_lower:
            return 'keyboards.shifts'
        elif 'keyboards/admin' in path_lower:
            return 'keyboards.admin'
        elif 'keyboards/' in path_lower:
            return 'keyboards'

        # Service sections
        elif 'services/notification' in path_lower:
            return 'notifications'
        elif 'services/request' in path_lower:
            return 'requests.service'
        elif 'services/shift' in path_lower:
            return 'shifts.service'
        elif 'services/auth' in path_lower:
            return 'auth.service'
        elif 'services/' in path_lower:
            return 'services'

        return 'common'

    def _normalize_string(self, text: str) -> str:
        """Normalize string to key-friendly format."""
        # Remove punctuation except spaces
        clean = re.sub(r'[^\w\s]', '', text.lower())
        # Replace spaces with underscores
        clean = re.sub(r'\s+', '_', clean.strip())
        # Remove multiple underscores
        clean = re.sub(r'_+', '_', clean)
        return clean

    def _transliterate(self, text: str) -> str:
        """Transliterate Russian/Uzbek to English where possible."""
        transliteration_map = {
            # Common words
            'привет': 'hello',
            'выберите': 'select',
            'выбрать': 'select',
            'введите': 'enter',
            'ввести': 'enter',
            'ошибка': 'error',
            'успешно': 'success',
            'успех': 'success',
            'отправить': 'send',
            'отправлено': 'sent',
            'отменить': 'cancel',
            'отменено': 'cancelled',
            'сохранить': 'save',
            'сохранено': 'saved',
            'удалить': 'delete',
            'удалено': 'deleted',
            'добавить': 'add',
            'добавлено': 'added',
            'изменить': 'edit',
            'изменено': 'edited',
            'создать': 'create',
            'создано': 'created',
            'обновить': 'update',
            'обновлено': 'updated',
            # Domain-specific
            'заявка': 'request',
            'заявки': 'requests',
            'смена': 'shift',
            'смены': 'shifts',
            'исполнитель': 'executor',
            'исполнители': 'executors',
            'менеджер': 'manager',
            'администратор': 'admin',
            'пользователь': 'user',
            'профиль': 'profile',
            'статус': 'status',
            'список': 'list',
            'назад': 'back',
            'далее': 'next',
            'готово': 'done',
            'да': 'yes',
            'нет': 'no',
            'подтвердить': 'confirm',
            'отклонить': 'reject',
            'принять': 'accept',
            'назначить': 'assign',
            'завершить': 'complete',
            'начать': 'start',
            'загрузить': 'upload',
            'скачать': 'download',
            'поиск': 'search',
            'фильтр': 'filter',
            'сортировка': 'sort',
            'уведомление': 'notification',
            'сообщение': 'message',
            'описание': 'description',
            'комментарий': 'comment',
            'адрес': 'address',
            'дата': 'date',
            'время': 'time',
            'период': 'period',
            'активный': 'active',
            'неактивный': 'inactive',
            'новый': 'new',
            'старый': 'old',
            'первый': 'first',
            'последний': 'last',
            'общий': 'total',
            'доступный': 'available',
            'недоступный': 'unavailable',
            'показать': 'show',
            'скрыть': 'hide',
            'открыть': 'open',
            'закрыть': 'close',
        }

        words = text.split('_')
        transliterated = []

        for word in words:
            if word in transliteration_map:
                transliterated.append(transliteration_map[word])
            else:
                # Keep original if no translation
                transliterated.append(word[:10])  # Max 10 chars per word

        return '_'.join(transliterated)[:50]  # Max 50 chars total

    def _ensure_unique_key(self, base_key: str, string_value: str) -> str:
        """Ensure key is unique, append suffix if needed."""
        # Check if key already exists with same value
        if base_key in self.existing_keys:
            existing_value = self.existing_keys[base_key]
            if existing_value == string_value:
                # Same key, same value - reuse
                self.stats['keys_existing'] += 1
                return base_key

            # Same key, different value - add suffix
            suffix = 2
            while f"{base_key}_{suffix}" in self.existing_keys:
                suffix += 1

            new_key = f"{base_key}_{suffix}"
            self.stats['conflicts_resolved'] += 1
            return new_key

        return base_key

    def process_scan_results(self, scan_results: List[Dict], mode: str = 'auto'):
        """Process scan results and generate locale entries."""
        print(f"📝 Processing {len(scan_results)} scan results in {mode} mode...")

        for result in scan_results:
            self.stats['total_processed'] += 1

            # Generate key
            suggested_key = result.get('suggestion', '')
            string_value = result['string_value']
            file_path = result['file_path']
            context = result.get('context', '')

            # Generate better key
            locale_key = self.generate_key(string_value, context, file_path)

            # In interactive mode, allow user to edit
            if mode == 'interactive':
                print(f"\n--- Entry {self.stats['total_processed']} ---")
                print(f"String: {string_value[:80]}")
                print(f"File: {file_path}:{result['line_number']}")
                print(f"Suggested: {locale_key}")
                user_key = input("Enter key (or press Enter to accept): ").strip()
                if user_key:
                    locale_key = user_key

            # Check if key already exists with same value
            if locale_key in self.existing_keys and self.existing_keys[locale_key] == string_value:
                continue  # Skip, already exists

            # Create entry
            entry = LocaleEntry(
                key=locale_key,
                ru_text=string_value,
                uz_text="[TRANSLATE]",  # Placeholder
                source_file=file_path,
                line_number=result['line_number'],
                context=context,
                priority=result.get('priority', 'P3')
            )

            self.new_entries.append(entry)
            self.existing_keys[locale_key] = string_value
            self.stats['keys_generated'] += 1

        print(f"✅ Processed {self.stats['total_processed']} entries")
        print(f"   Generated: {self.stats['keys_generated']} new keys")
        print(f"   Existing: {self.stats['keys_existing']} keys reused")
        print(f"   Conflicts: {self.stats['conflicts_resolved']} resolved")

    def update_locale_files(self, dry_run: bool = False):
        """Update ru.json and uz.json with new entries."""
        if not self.new_entries:
            print("ℹ️  No new entries to add")
            return

        print(f"\n📝 Updating locale files with {len(self.new_entries)} new entries...")

        # Prepare flat dicts with new entries
        ru_flat = self._flatten_keys(self.ru_locale)
        uz_flat = self._flatten_keys(self.uz_locale)

        for entry in self.new_entries:
            ru_flat[entry.key] = entry.ru_text

            # Only add placeholder if key doesn't exist in UZ
            if entry.key not in uz_flat:
                uz_flat[entry.key] = entry.uz_text

        # Convert back to nested
        ru_nested = self._unflatten_keys(ru_flat)
        uz_nested = self._unflatten_keys(uz_flat)

        # Sort keys recursively
        ru_sorted = self._sort_dict_recursive(ru_nested)
        uz_sorted = self._sort_dict_recursive(uz_nested)

        if dry_run:
            print("🔍 DRY RUN - Would update:")
            print(f"   {self.ru_locale_path}")
            print(f"   {self.uz_locale_path}")
            return

        # Backup existing files
        if self.ru_locale_path.exists():
            backup_path = self.ru_locale_path.with_suffix('.json.backup')
            backup_path.write_text(self.ru_locale_path.read_text(), encoding='utf-8')
            print(f"📦 Backup: {backup_path}")

        if self.uz_locale_path.exists():
            backup_path = self.uz_locale_path.with_suffix('.json.backup')
            backup_path.write_text(self.uz_locale_path.read_text(), encoding='utf-8')
            print(f"📦 Backup: {backup_path}")

        # Write updated locale files
        with open(self.ru_locale_path, 'w', encoding='utf-8') as f:
            json.dump(ru_sorted, f, ensure_ascii=False, indent=2)

        with open(self.uz_locale_path, 'w', encoding='utf-8') as f:
            json.dump(uz_sorted, f, ensure_ascii=False, indent=2)

        print(f"✅ Updated {self.ru_locale_path}")
        print(f"✅ Updated {self.uz_locale_path}")

    def _sort_dict_recursive(self, d: Dict) -> Dict:
        """Sort dictionary keys recursively."""
        sorted_dict = {}
        for key in sorted(d.keys()):
            if isinstance(d[key], dict):
                sorted_dict[key] = self._sort_dict_recursive(d[key])
            else:
                sorted_dict[key] = d[key]
        return sorted_dict

    def generate_mapping_file(self, output_path: Path):
        """Generate mapping file for migration reference."""
        print(f"\n📝 Generating mapping file...")

        mapping = []
        for entry in self.new_entries:
            mapping.append({
                'key': entry.key,
                'ru_text': entry.ru_text,
                'uz_text': entry.uz_text,
                'source': f"{entry.source_file}:{entry.line_number}",
                'priority': entry.priority,
                'context': entry.context
            })

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)

        print(f"✅ Mapping saved to {output_path}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate locale keys from scan results")
    parser.add_argument('--input', default='hardcoded_strings_scan.json',
                       help='Input JSON from scan_hardcoded_strings.py')
    parser.add_argument('--mode', choices=['auto', 'interactive'], default='auto',
                       help='Processing mode')
    parser.add_argument('--ru-locale', default='uk_management_bot/locales/ru.json',
                       help='Path to ru.json')
    parser.add_argument('--uz-locale', default='uk_management_bot/locales/uz.json',
                       help='Path to uz.json')
    parser.add_argument('--output-mapping', default='locale_key_mapping.json',
                       help='Output mapping file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Dry run without updating files')

    args = parser.parse_args()

    # Load scan results
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1

    with open(input_path, 'r', encoding='utf-8') as f:
        scan_results = json.load(f)

    print(f"📖 Loaded {len(scan_results)} scan results from {input_path}")

    # Initialize generator
    generator = LocaleKeyGenerator(
        ru_locale_path=Path(args.ru_locale),
        uz_locale_path=Path(args.uz_locale)
    )

    # Process results
    generator.process_scan_results(scan_results, mode=args.mode)

    # Update locale files
    generator.update_locale_files(dry_run=args.dry_run)

    # Generate mapping
    generator.generate_mapping_file(Path(args.output_mapping))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total processed: {generator.stats['total_processed']}")
    print(f"New keys generated: {generator.stats['keys_generated']}")
    print(f"Existing keys reused: {generator.stats['keys_existing']}")
    print(f"Conflicts resolved: {generator.stats['conflicts_resolved']}")
    print()

    if args.dry_run:
        print("⚠️  DRY RUN - No files were modified")
    else:
        print("✅ Locale files updated successfully")

    return 0


if __name__ == '__main__':
    exit(main())
