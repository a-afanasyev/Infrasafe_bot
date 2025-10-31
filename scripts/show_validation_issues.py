#!/usr/bin/env python3
"""
Выводит детали проблем валидации переводов для ручного исправления.
"""

import json
import re
from pathlib import Path
from typing import Dict, Set, Tuple

def flatten_keys(nested_dict: Dict, prefix: str = '') -> Dict[str, str]:
    """Flatten nested locale dictionary."""
    flat = {}
    for key, value in nested_dict.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_keys(value, full_key))
        else:
            flat[full_key] = value
    return flat

def find_format_params(text: str) -> Set[str]:
    """Find all format parameters in text."""
    pattern = re.compile(r'\{(\w+)\}')
    return set(pattern.findall(text))

def main():
    ru_path = Path('uk_management_bot/config/locales/ru.json')
    uz_path = Path('uk_management_bot/config/locales/uz.json')
    
    with open(ru_path, 'r', encoding='utf-8') as f:
        ru_locale = json.load(f)
    with open(uz_path, 'r', encoding='utf-8') as f:
        uz_locale = json.load(f)
    
    ru_flat = flatten_keys(ru_locale)
    uz_flat = flatten_keys(uz_locale)
    
    print("=" * 80)
    print("DETAILED VALIDATION ISSUES")
    print("=" * 80)
    print()
    
    # Format mismatches
    print("🔴 FORMAT MISMATCHES:")
    print("-" * 80)
    format_mismatches = []
    for key in sorted(ru_flat.keys()):
        if key not in uz_flat:
            continue
        
        ru_value = ru_flat[key]
        uz_value = uz_flat[key]
        
        if '[TRANSLATE]' in uz_value:
            continue
        
        ru_params = find_format_params(ru_value)
        uz_params = find_format_params(uz_value)
        
        if ru_params != uz_params:
            format_mismatches.append((key, ru_params, uz_params, ru_value, uz_value))
            print(f"\nKey: {key}")
            print(f"  RU params: {sorted(ru_params)}")
            print(f"  UZ params: {sorted(uz_params)}")
            print(f"  RU: {ru_value}")
            print(f"  UZ: {uz_value}")
    
    print(f"\nTotal format mismatches: {len(format_mismatches)}")
    print()
    
    # Extra keys
    print("=" * 80)
    print("🟡 EXTRA KEYS IN UZ:")
    print("-" * 80)
    extra_keys = set(uz_flat.keys()) - set(ru_flat.keys())
    for key in sorted(extra_keys):
        print(f"  {key}: {uz_flat[key]}")
    
    print(f"\nTotal extra keys: {len(extra_keys)}")
    print()

if __name__ == '__main__':
    main()

