#!/usr/bin/env python3
"""
Script to remove legacy address-related keys from localization files.
TASK 17 Phase 2 - Session 42: Localization Cleanup
"""

import json
import sys
from pathlib import Path

# Keys to remove (legacy address input system)
KEYS_TO_REMOVE = [
    # Profile section - manual address input
    "apartment_address_updated",
    "enter_apartment_address",
    "enter_home_address",
    "enter_yard_address",
    "home_address_updated",
    "yard_address_updated",

    # Requests section - manual address input
    "enter_address_manually",
]

def remove_keys_from_json(json_obj, keys_to_remove):
    """Recursively remove keys from JSON object"""
    removed_count = 0

    if isinstance(json_obj, dict):
        # Create list of keys to avoid runtime dictionary change error
        keys_list = list(json_obj.keys())

        for key in keys_list:
            if key in keys_to_remove:
                del json_obj[key]
                removed_count += 1
                print(f"  ✓ Removed key: {key}")
            else:
                # Recursively process nested dictionaries
                removed_count += remove_keys_from_json(json_obj[key], keys_to_remove)

    return removed_count

def cleanup_locale_file(file_path: Path, keys_to_remove: list) -> int:
    """Clean up a single locale file"""
    print(f"\n📄 Processing: {file_path.name}")

    # Read JSON file
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Remove keys
    removed_count = remove_keys_from_json(data, keys_to_remove)

    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Removed {removed_count} keys from {file_path.name}")
    return removed_count

def main():
    """Main execution"""
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    locales_dir = project_root / "uk_management_bot" / "config" / "locales"

    # Files to process
    locale_files = [
        locales_dir / "ru.json",
        locales_dir / "uz.json",
    ]

    print("🧹 Starting localization cleanup...")
    print(f"Keys to remove: {len(KEYS_TO_REMOVE)}")
    print(f"  • {', '.join(KEYS_TO_REMOVE[:3])}")
    print(f"  • ... and {len(KEYS_TO_REMOVE) - 3} more")

    total_removed = 0

    for locale_file in locale_files:
        if not locale_file.exists():
            print(f"⚠️  Skipping {locale_file.name} (not found)")
            continue

        removed = cleanup_locale_file(locale_file, KEYS_TO_REMOVE)
        total_removed += removed

    print(f"\n✅ Cleanup complete!")
    print(f"📊 Total keys removed: {total_removed}")
    print(f"📁 Files processed: {len([f for f in locale_files if f.exists()])}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
