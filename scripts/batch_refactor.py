#!/usr/bin/env python3
"""
Batch Refactor Script - TASK 17 Phase 2
Делает batch замены хардкодных строк на get_text() вызовы на основе mapping файла.

Использование:
    python scripts/batch_refactor.py --file handlers/requests.py --mapping mappings/handlers_mapping.json --dry-run
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


def load_mapping(mapping_file: Path, handler_file: Path) -> Dict[int, Dict]:
    """Загружает mapping для конкретного файла."""
    with open(mapping_file, 'r', encoding='utf-8') as f:
        mapping_data = json.load(f)
    
    file_mappings = {}
    handler_name = handler_file.name
    
    for item in mapping_data:
        source = item.get('source', '')
        if handler_name in source:
            # Извлекаем номер строки
            match = re.search(r':(\d+)$', source)
            if match:
                line_num = int(match.group(1))
                file_mappings[line_num] = {
                    'key': item['key'],
                    'ru_text': item.get('ru_text', ''),
                    'context': item.get('context', '')
                }
    
    return file_mappings


def find_string_in_file(content: str, ru_text: str, line_num: int) -> Tuple[int, str]:
    """Находит строку в файле и возвращает индекс строки и найденный текст."""
    lines = content.split('\n')
    line_idx = line_num - 1  # 0-based
    
    if line_idx >= len(lines):
        return None, None
    
    line = lines[line_idx]
    
    # Ищем строку в разных форматах
    patterns = [
        (f'"{re.escape(ru_text)}"', f'"{ru_text}"'),
        (f"'{re.escape(ru_text)}'", f"'{ru_text}'"),
        (f'f"{re.escape(ru_text)}"', f'f"{ru_text}"'),
        (f"f'{re.escape(ru_text)}'", f"f'{ru_text}'"),
    ]
    
    # Также ищем части строки для многострочных
    first_part = None
    if len(ru_text) > 50:
        first_part = ru_text[:50]
        patterns.append((first_part, ru_text))
    
    for pattern, full_text in patterns:
        if pattern in line or (first_part and first_part in line):
            return line_idx, full_text
    
    return None, None


def replace_string_in_line(line: str, old_text: str, locale_key: str) -> Tuple[str, bool]:
    """Заменяет строку в строке кода."""
    # Проверяем контекст - должны быть await и answer/edit_text/reply
    if 'await' not in line or ('answer' not in line and 'edit_text' not in line and 'reply' not in line):
        return line, False
    
    # Простая замена в кавычках
    if f'"{old_text}"' in line:
        new_text = f'get_text("{locale_key}", language=lang)'
        return line.replace(f'"{old_text}"', new_text), True
    elif f"'{old_text}'" in line:
        new_text = f'get_text("{locale_key}", language=lang)'
        return line.replace(f"'{old_text}'", new_text), True
    
    # Многострочная строка
    if old_text[:30] in line:
        # Находим начало строки
        pattern = re.escape(old_text[:30])
        new_text = f'get_text("{locale_key}", language=lang)'
        # Пытаемся заменить начало
        new_line = re.sub(pattern, new_text, line, count=1)
        if new_line != line:
            return new_line, True
    
    return line, False


def batch_refactor(handler_file: Path, mapping_file: Path, dry_run: bool = False) -> int:
    """Выполняет batch рефакторинг."""
    print(f"🔧 Batch Refactoring {handler_file.name}...")
    print(f"📋 Using mapping: {mapping_file.name}")
    
    # Загружаем mapping
    file_mappings = load_mapping(mapping_file, handler_file)
    print(f"📊 Found {len(file_mappings)} mappings for this file\n")
    
    if not file_mappings:
        print("⚠️  No mappings found")
        return 0
    
    # Читаем файл
    with open(handler_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    replacements_made = 0
    
    # Собираем замены
    replacements = []
    for line_num, mapping_info in sorted(file_mappings.items()):
        ru_text = mapping_info['ru_text']
        locale_key = mapping_info['key']
        
        line_idx, found_text = find_string_in_file(content, ru_text, line_num)
        
        if line_idx is not None and line_idx < len(lines):
            line = lines[line_idx]
            new_line, replaced = replace_string_in_line(line, found_text or ru_text, locale_key)
            
            if replaced:
                replacements.append((line_idx, line, new_line, locale_key))
    
    if not replacements:
        print("⚠️  No suitable replacements found")
        return 0
    
    print(f"✅ Found {len(replacements)} replacements:\n")
    
    # Показываем что будет заменено
    for line_idx, old_line, new_line, locale_key in replacements[:10]:
        print(f"Line {line_idx + 1}:")
        print(f"  Old: {old_line[:80]}...")
        print(f"  New: {new_line[:80]}...")
        print(f"  Key: {locale_key}\n")
    
    if len(replacements) > 10:
        print(f"  ... and {len(replacements) - 10} more replacements\n")
    
    if dry_run:
        print("🔍 DRY RUN - No changes made")
        return len(replacements)
    
    # Выполняем замены (в обратном порядке)
    for line_idx, old_line, new_line, locale_key in reversed(replacements):
        lines[line_idx] = new_line
        replacements_made += 1
    
    # Сохраняем файл
    if replacements_made > 0:
        backup_path = handler_file.with_suffix(f'.{handler_file.suffix}.backup_batch')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"📦 Backup created: {backup_path}")
        
        new_content = '\n'.join(lines)
        with open(handler_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"💾 Saved: {handler_file}")
        print(f"✅ Made {replacements_made} replacements")
    
    return replacements_made


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Batch refactor handler files")
    parser.add_argument('--file', required=True, help='Handler file to refactor')
    parser.add_argument('--mapping', default='mappings/handlers_mapping.json',
                       help='Mapping file path')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be changed without making changes')
    
    args = parser.parse_args()
    
    handler_file = Path(args.file)
    mapping_file = Path(args.mapping)
    
    if not handler_file.exists():
        print(f"❌ Handler file not found: {handler_file}")
        return 1
    
    if not mapping_file.exists():
        print(f"❌ Mapping file not found: {mapping_file}")
        return 1
    
    replacements = batch_refactor(handler_file, mapping_file, args.dry_run)
    
    if replacements > 0:
        print(f"\n✅ Batch refactoring complete: {replacements} replacements")
        return 0
    else:
        print("\n⚠️  No replacements made")
        return 0


if __name__ == '__main__':
    exit(main())

