#!/usr/bin/env python3
"""
Translation Validator - TASK 17 Phase 1
Validates translation files for consistency, completeness, and quality.

Usage:
    python scripts/validate_translations.py [--fix] [--report REPORT_PATH]

Features:
    - Validates ru.json ↔ uz.json synchronization (100% key parity)
    - Detects missing translations ([TRANSLATE] placeholders)
    - Checks for format string consistency ({param} matching)
    - Validates nested structure integrity
    - Detects duplicate values (possible key consolidation)
    - Reports untranslated strings by priority
    - Auto-fix mode for common issues
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    severity: str  # 'error', 'warning', 'info'
    category: str  # 'missing_key', 'missing_translation', 'format_mismatch', etc.
    key: str
    message: str
    details: Dict = field(default_factory=dict)


class TranslationValidator:
    """Validates translation files."""

    def __init__(self, ru_locale_path: Path, uz_locale_path: Path):
        self.ru_locale_path = ru_locale_path
        self.uz_locale_path = uz_locale_path

        # Load locales
        self.ru_locale = self._load_locale(ru_locale_path)
        self.uz_locale = self._load_locale(uz_locale_path)

        # Flatten for easier comparison
        self.ru_flat = self._flatten_keys(self.ru_locale)
        self.uz_flat = self._flatten_keys(self.uz_locale)

        # Issues found
        self.issues: List[ValidationIssue] = []

        # Statistics
        self.stats = {
            'total_keys': 0,
            'errors': 0,
            'warnings': 0,
            'info': 0,
            'missing_translations': 0,
            'format_mismatches': 0,
            'missing_keys_uz': 0,
            'extra_keys_uz': 0,
        }

    def _load_locale(self, path: Path) -> Dict:
        """Load locale JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"Locale file not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _flatten_keys(self, nested_dict: Dict, prefix: str = '') -> Dict[str, str]:
        """Flatten nested locale dictionary."""
        flat = {}

        for key, value in nested_dict.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                flat.update(self._flatten_keys(value, full_key))
            else:
                flat[full_key] = value

        return flat

    def _unflatten_keys(self, flat_dict: Dict[str, str]) -> Dict:
        """Convert flat dict to nested dict."""
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

    def validate_key_parity(self):
        """Validate that ru.json and uz.json have same keys."""
        print("🔍 Validating key parity...")

        ru_keys = set(self.ru_flat.keys())
        uz_keys = set(self.uz_flat.keys())

        # Missing in UZ
        missing_in_uz = ru_keys - uz_keys
        if missing_in_uz:
            for key in sorted(missing_in_uz):
                self.issues.append(ValidationIssue(
                    severity='error',
                    category='missing_key_uz',
                    key=key,
                    message=f"Key exists in ru.json but missing in uz.json",
                    details={'ru_value': self.ru_flat[key]}
                ))
                self.stats['missing_keys_uz'] += 1

        # Extra in UZ
        extra_in_uz = uz_keys - ru_keys
        if extra_in_uz:
            for key in sorted(extra_in_uz):
                self.issues.append(ValidationIssue(
                    severity='warning',
                    category='extra_key_uz',
                    key=key,
                    message=f"Key exists in uz.json but missing in ru.json",
                    details={'uz_value': self.uz_flat[key]}
                ))
                self.stats['extra_keys_uz'] += 1

        self.stats['total_keys'] = len(ru_keys)

        if not missing_in_uz and not extra_in_uz:
            print(f"   ✅ Perfect parity: {len(ru_keys)} keys in both files")
        else:
            print(f"   ⚠️  Missing in UZ: {len(missing_in_uz)}")
            print(f"   ⚠️  Extra in UZ: {len(extra_in_uz)}")

    def validate_translations(self):
        """Validate that all strings are translated (no [TRANSLATE] placeholders)."""
        print("🔍 Validating translations...")

        untranslated = []

        for key, value in self.uz_flat.items():
            if isinstance(value, str) and ('[TRANSLATE]' in value or value == self.ru_flat.get(key)):
                # Check if it's actually the same as Russian (might be intentional)
                if value == '[TRANSLATE]' or (value.startswith('[TRANSLATE]') and value.endswith(']')):
                    untranslated.append(key)
                    self.issues.append(ValidationIssue(
                        severity='warning',
                        category='missing_translation',
                        key=key,
                        message=f"String not translated (placeholder: {value})",
                        details={'ru_value': self.ru_flat.get(key, ''), 'uz_value': value}
                    ))
                    self.stats['missing_translations'] += 1

        if not untranslated:
            print(f"   ✅ All strings translated")
        else:
            print(f"   ⚠️  Untranslated: {len(untranslated)} strings")

    def validate_format_strings(self):
        """Validate that format strings {param} match between RU and UZ."""
        print("🔍 Validating format strings...")

        format_pattern = re.compile(r'\{(\w+)\}')

        mismatches = []

        for key in self.ru_flat.keys():
            if key not in self.uz_flat:
                continue  # Already caught by parity check

            ru_value = self.ru_flat[key]
            uz_value = self.uz_flat[key]

            # Skip placeholders
            if '[TRANSLATE]' in uz_value:
                continue

            # Extract format params
            ru_params = set(format_pattern.findall(ru_value))
            uz_params = set(format_pattern.findall(uz_value))

            if ru_params != uz_params:
                mismatches.append(key)
                self.issues.append(ValidationIssue(
                    severity='error',
                    category='format_mismatch',
                    key=key,
                    message=f"Format string parameters don't match",
                    details={
                        'ru_params': sorted(ru_params),
                        'uz_params': sorted(uz_params),
                        'ru_value': ru_value,
                        'uz_value': uz_value
                    }
                ))
                self.stats['format_mismatches'] += 1

        if not mismatches:
            print(f"   ✅ All format strings valid")
        else:
            print(f"   ❌ Format mismatches: {len(mismatches)}")

    def validate_structure(self):
        """Validate nested structure integrity."""
        print("🔍 Validating structure...")

        # Check that nested dicts are consistent
        ru_sections = set()
        uz_sections = set()

        def extract_sections(flat_dict: Dict[str, str]) -> Set[str]:
            sections = set()
            for key in flat_dict.keys():
                parts = key.split('.')
                for i in range(len(parts)):
                    sections.add('.'.join(parts[:i+1]))
            return sections

        ru_sections = extract_sections(self.ru_flat)
        uz_sections = extract_sections(self.uz_flat)

        # Should be identical
        if ru_sections == uz_sections:
            print(f"   ✅ Structure consistent: {len(ru_sections)} nodes")
        else:
            missing = ru_sections - uz_sections
            extra = uz_sections - ru_sections
            print(f"   ⚠️  Structure mismatch:")
            print(f"       Missing in UZ: {len(missing)}")
            print(f"       Extra in UZ: {len(extra)}")

            for section in missing:
                self.issues.append(ValidationIssue(
                    severity='info',
                    category='structure_mismatch',
                    key=section,
                    message=f"Section exists in RU but not in UZ",
                    details={}
                ))

    def detect_duplicates(self):
        """Detect duplicate values (possible key consolidation opportunities)."""
        print("🔍 Detecting duplicates...")

        ru_value_to_keys = defaultdict(list)
        uz_value_to_keys = defaultdict(list)

        for key, value in self.ru_flat.items():
            if isinstance(value, str) and len(value.strip()) > 5:  # Skip short strings
                ru_value_to_keys[value].append(key)

        for key, value in self.uz_flat.items():
            if isinstance(value, str) and len(value.strip()) > 5 and '[TRANSLATE]' not in value:
                uz_value_to_keys[value].append(key)

        ru_duplicates = {v: ks for v, ks in ru_value_to_keys.items() if len(ks) > 1}
        uz_duplicates = {v: ks for v, ks in uz_value_to_keys.items() if len(ks) > 1}

        if ru_duplicates:
            print(f"   ℹ️  RU duplicates: {len(ru_duplicates)} values used multiple times")
            for value, keys in list(ru_duplicates.items())[:5]:  # Show top 5
                self.issues.append(ValidationIssue(
                    severity='info',
                    category='duplicate_value_ru',
                    key=', '.join(keys[:3]),
                    message=f"Duplicate RU value in {len(keys)} keys",
                    details={'value': value[:50], 'keys': keys}
                ))

        if uz_duplicates:
            print(f"   ℹ️  UZ duplicates: {len(uz_duplicates)} values used multiple times")

    def generate_statistics(self) -> Dict:
        """Generate validation statistics."""
        total_issues = len(self.issues)

        for issue in self.issues:
            if issue.severity == 'error':
                self.stats['errors'] += 1
            elif issue.severity == 'warning':
                self.stats['warnings'] += 1
            else:
                self.stats['info'] += 1

        return self.stats

    def fix_common_issues(self):
        """Auto-fix common issues."""
        print("\n🔧 Attempting auto-fixes...")

        fixed = 0

        # Fix 1: Add missing keys to UZ with [TRANSLATE] placeholder
        for issue in self.issues:
            if issue.category == 'missing_key_uz':
                key = issue.key
                ru_value = issue.details['ru_value']
                self.uz_flat[key] = '[TRANSLATE]'
                fixed += 1

        # Fix 2: Remove extra keys from UZ (if they don't look important)
        # (Conservative: only remove if value is [TRANSLATE])
        for issue in self.issues:
            if issue.category == 'extra_key_uz':
                key = issue.key
                if self.uz_flat.get(key) == '[TRANSLATE]':
                    del self.uz_flat[key]
                    fixed += 1

        print(f"   ✅ Fixed {fixed} issues")

        return fixed

    def save_fixed_locales(self):
        """Save fixed locale files."""
        print("\n💾 Saving fixed locale files...")

        # Convert back to nested
        uz_nested = self._unflatten_keys(self.uz_flat)

        # Sort
        uz_sorted = self._sort_dict_recursive(uz_nested)

        # Backup
        backup_path = self.uz_locale_path.with_suffix('.json.backup')
        if self.uz_locale_path.exists():
            backup_path.write_text(self.uz_locale_path.read_text(), encoding='utf-8')
            print(f"   📦 Backup: {backup_path}")

        # Write
        with open(self.uz_locale_path, 'w', encoding='utf-8') as f:
            json.dump(uz_sorted, f, ensure_ascii=False, indent=2)

        print(f"   ✅ Saved {self.uz_locale_path}")

    def _sort_dict_recursive(self, d: Dict) -> Dict:
        """Sort dictionary recursively."""
        sorted_dict = {}
        for key in sorted(d.keys()):
            if isinstance(d[key], dict):
                sorted_dict[key] = self._sort_dict_recursive(d[key])
            else:
                sorted_dict[key] = d[key]
        return sorted_dict

    def generate_report(self, output_path: Path):
        """Generate validation report."""
        print(f"\n📝 Generating validation report...")

        lines = []
        lines.append("=" * 80)
        lines.append("TRANSLATION VALIDATION REPORT - TASK 17 Phase 1")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total keys: {self.stats['total_keys']}")
        lines.append(f"Total issues: {len(self.issues)}")
        lines.append(f"  Errors: {self.stats['errors']}")
        lines.append(f"  Warnings: {self.stats['warnings']}")
        lines.append(f"  Info: {self.stats['info']}")
        lines.append("")

        # Detailed stats
        lines.append("DETAILED STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Missing translations: {self.stats['missing_translations']}")
        lines.append(f"Format mismatches: {self.stats['format_mismatches']}")
        lines.append(f"Missing keys (UZ): {self.stats['missing_keys_uz']}")
        lines.append(f"Extra keys (UZ): {self.stats['extra_keys_uz']}")
        lines.append("")

        # Group issues by category
        by_category = defaultdict(list)
        for issue in self.issues:
            by_category[issue.category].append(issue)

        lines.append("ISSUES BY CATEGORY")
        lines.append("-" * 80)
        for category in sorted(by_category.keys()):
            issues = by_category[category]
            lines.append(f"\n{category.upper()} ({len(issues)} issues):")
            for issue in issues[:20]:  # Limit to 20 per category
                lines.append(f"  [{issue.severity.upper()}] {issue.key}")
                lines.append(f"     {issue.message}")
                if issue.details:
                    for k, v in issue.details.items():
                        if isinstance(v, (list, dict)):
                            lines.append(f"     {k}: {v}")
                        else:
                            lines.append(f"     {k}: {str(v)[:80]}")
                lines.append("")

        report_text = "\n".join(lines)

        output_path.write_text(report_text, encoding='utf-8')
        print(f"   ✅ Report saved to {output_path}")

        return report_text


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate translation files")
    parser.add_argument('--ru-locale', default='uk_management_bot/locales/ru.json',
                       help='Path to ru.json')
    parser.add_argument('--uz-locale', default='uk_management_bot/locales/uz.json',
                       help='Path to uz.json')
    parser.add_argument('--fix', action='store_true',
                       help='Auto-fix common issues')
    parser.add_argument('--report', default='translation_validation_report.txt',
                       help='Output report path')

    args = parser.parse_args()

    print("🔍 Translation Validator - TASK 17 Phase 1")
    print("=" * 80)
    print()

    # Initialize validator
    validator = TranslationValidator(
        ru_locale_path=Path(args.ru_locale),
        uz_locale_path=Path(args.uz_locale)
    )

    # Run validations
    validator.validate_key_parity()
    validator.validate_translations()
    validator.validate_format_strings()
    validator.validate_structure()
    validator.detect_duplicates()

    # Generate statistics
    stats = validator.generate_statistics()

    # Generate report
    print()
    validator.generate_report(Path(args.report))

    # Auto-fix if requested
    if args.fix:
        fixed = validator.fix_common_issues()
        if fixed > 0:
            validator.save_fixed_locales()

    # Print summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Total keys: {stats['total_keys']}")
    print(f"Total issues: {len(validator.issues)}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Warnings: {stats['warnings']}")
    print(f"  Info: {stats['info']}")
    print()

    if stats['errors'] > 0:
        print("❌ Validation failed with errors")
        return 1
    elif stats['warnings'] > 0:
        print("⚠️  Validation passed with warnings")
        return 0
    else:
        print("✅ Validation passed successfully")
        return 0


if __name__ == '__main__':
    exit(main())
