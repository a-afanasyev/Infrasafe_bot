#!/usr/bin/env python3
"""
Refactor Handler Script - TASK 17 Phase 2
Автоматизирует рефакторинг handler файлов для использования get_text() вместо хардкодных строк.

Использование:
    python scripts/refactor_handler.py --file handlers/requests.py --mapping mappings/handlers_mapping.json
    
Функционал:
    - Заменяет хардкодные строки на get_text() вызовы
    - Добавляет импорты get_text и get_language_for_user
    - Добавляет получение языка в функции handlers
    - Сохраняет бэкап перед изменениями
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import shutil


class HandlerRefactorer:
    """Рефакторинг handler файлов для локализации."""
    
    def __init__(self, handler_file: Path, mapping_file: Path):
        self.handler_file = handler_file
        self.mapping_file = mapping_file
        
        # Загружаем mapping
        with open(mapping_file, 'r', encoding='utf-8') as f:
            self.mapping_data = json.load(f)
        
        # Группируем по файлам
        self.file_mappings = defaultdict(list)
        for item in self.mapping_data:
            source = item.get('source', '')
            if str(handler_file) in source or handler_file.name in source:
                self.file_mappings[item['key']] = item
        
        # Читаем исходный файл
        with open(handler_file, 'r', encoding='utf-8') as f:
            self.content = f.read()
            self.lines = self.content.split('\n')
        
        self.changes_made = []
        self.imports_added = set()
    
    def add_imports(self):
        """Добавляет необходимые импорты."""
        imports_to_add = [
            'from uk_management_bot.utils.helpers import get_text',
            'from uk_management_bot.utils.language_helpers import get_language_for_user'
        ]
        
        # Проверяем какие импорты уже есть
        has_get_text = 'from uk_management_bot.utils.helpers import get_text' in self.content
        has_get_language = 'from uk_management_bot.utils.language_helpers import get_language_for_user' in self.content
        
        # Находим место для вставки импортов (после последнего импорта)
        import_pattern = re.compile(r'^(from|import) ')
        last_import_line = -1
        
        for i, line in enumerate(self.lines):
            if import_pattern.match(line.strip()):
                last_import_line = i
        
        if last_import_line == -1:
            # Нет импортов, добавляем в начало
            insert_line = 0
        else:
            insert_line = last_import_line + 1
        
        # Добавляем импорты
        lines_to_insert = []
        if not has_get_text:
            lines_to_insert.append(imports_to_add[0])
            self.imports_added.add('get_text')
        if not has_get_language:
            lines_to_insert.append(imports_to_add[1])
            self.imports_added.add('get_language_for_user')
        
        if lines_to_insert:
            # Добавляем пустую строку если нужно
            if insert_line < len(self.lines) and self.lines[insert_line].strip():
                lines_to_insert.insert(0, '')
            
            self.lines.insert(insert_line, '\n'.join(lines_to_insert))
            self.changes_made.append(f"Added imports: {', '.join(lines_to_insert)}")
    
    def find_string_replacements(self) -> List[Tuple[int, str, str]]:
        """Находит строки для замены."""
        replacements = []
        
        for key, mapping_item in self.file_mappings.items():
            ru_text = mapping_item.get('ru_text', '')
            source = mapping_item.get('source', '')
            
            # Извлекаем номер строки из source
            match = re.search(r':(\d+)', source)
            if not match:
                continue
            
            line_num = int(match.group(1)) - 1  # 0-based index
            
            if line_num >= len(self.lines):
                continue
            
            # Ищем строку в файле
            line = self.lines[line_num]
            
            # Ищем различные паттерны использования строки
            patterns = [
                (rf'["\']{re.escape(ru_text[:50])}.*?["\']', key),  # Прямая строка
                (rf'f["\']{re.escape(ru_text[:50])}.*?["\']', key),  # f-string
            ]
            
            for pattern, locale_key in patterns:
                if re.search(pattern, line):
                    # Находим полную строку
                    full_match = re.search(pattern, line)
                    if full_match:
                        old_string = full_match.group(0)
                        # Заменяем на get_text вызов
                        # Но нужно учитывать контекст - где используется
                        replacements.append((line_num, old_string, locale_key))
                        break
        
        return replacements
    
    def add_language_parameter(self, func_start_line: int) -> bool:
        """Добавляет получение языка в функцию."""
        # Ищем сигнатуру функции
        func_pattern = re.compile(r'^\s*(async\s+)?def\s+\w+\s*\(')
        
        # Ищем параметры функции
        in_func = False
        func_end_line = func_start_line
        
        for i in range(func_start_line, min(func_start_line + 50, len(self.lines))):
            line = self.lines[i]
            
            if func_pattern.match(line):
                in_func = True
                # Проверяем есть ли уже language параметр
                if 'language' in line.lower() or 'lang' in line.lower():
                    return False  # Уже есть
            
            if in_func:
                # Ищем начало тела функции
                if ':' in line and not line.strip().startswith('#'):
                    func_end_line = i
                    break
        
        # Проверяем есть ли db параметр
        func_line = self.lines[func_start_line]
        has_db = 'db' in func_line or 'session' in func_line
        
        if not has_db:
            return False  # Не можем получить язык без db
        
        # Добавляем получение языка в начало функции
        indent = len(self.lines[func_end_line + 1]) - len(self.lines[func_end_line + 1].lstrip())
        
        # Определяем способ получения языка
        if 'callback' in func_line.lower():
            language_code = f"lang = await get_language_for_user(callback.from_user.id, db, callback)"
        elif 'message' in func_line.lower():
            language_code = f"lang = await get_language_for_user(message.from_user.id, db, message)"
        else:
            return False  # Не знаем как получить
        
        # Вставляем получение языка
        insert_line = func_end_line + 1
        self.lines.insert(insert_line, ' ' * indent + language_code)
        self.changes_made.append(f"Added language detection at line {insert_line + 1}")
        
        return True
    
    def refactor(self) -> bool:
        """Выполняет рефакторинг."""
        if not self.file_mappings:
            print(f"⚠️  No mappings found for {self.handler_file.name}")
            return False
        
        # Добавляем импорты
        self.add_imports()
        
        # Находим замены
        replacements = self.find_string_replacements()
        
        if not replacements:
            print(f"⚠️  No string replacements found for {self.handler_file.name}")
            return False
        
        # Выполняем замены (в обратном порядке чтобы не сбить индексы)
        for line_num, old_string, locale_key in reversed(replacements):
            line = self.lines[line_num]
            
            # Пытаемся найти контекст использования
            if 'await' in line and ('answer' in line or 'edit_text' in line or 'reply' in line):
                # Это вызов bot API
                # Заменяем строку на get_text вызов
                new_string = f'get_text("{locale_key}", language=lang)'
                
                # Простая замена в кавычках
                if old_string.startswith('"') and old_string.endswith('"'):
                    line = line.replace(old_string, new_string)
                elif old_string.startswith("'") and old_string.endswith("'"):
                    line = line.replace(old_string, new_string)
                else:
                    # Более сложная замена
                    # Пытаемся найти строку в контексте
                    pattern = re.escape(old_string[:30])
                    line = re.sub(pattern, new_string, line, count=1)
                
                self.lines[line_num] = line
                self.changes_made.append(f"Line {line_num + 1}: replaced string with {locale_key}")
        
        return len(self.changes_made) > 0
    
    def save(self, backup: bool = True):
        """Сохраняет изменения."""
        if backup:
            backup_path = self.handler_file.with_suffix(f'.{self.handler_file.suffix}.backup')
            shutil.copy2(self.handler_file, backup_path)
            print(f"📦 Backup created: {backup_path}")
        
        # Сохраняем файл
        new_content = '\n'.join(self.lines)
        with open(self.handler_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"💾 Saved: {self.handler_file}")
        print(f"✅ Made {len(self.changes_made)} changes")
        for change in self.changes_made[:10]:  # Показываем первые 10
            print(f"   - {change}")
        if len(self.changes_made) > 10:
            print(f"   ... and {len(self.changes_made) - 10} more")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Refactor handler files for localization")
    parser.add_argument('--file', required=True, help='Handler file to refactor')
    parser.add_argument('--mapping', default='mappings/handlers_mapping.json',
                       help='Mapping file path')
    parser.add_argument('--no-backup', action='store_true',
                       help='Skip backup creation')
    
    args = parser.parse_args()
    
    handler_file = Path(args.file)
    mapping_file = Path(args.mapping)
    
    if not handler_file.exists():
        print(f"❌ Handler file not found: {handler_file}")
        return 1
    
    if not mapping_file.exists():
        print(f"❌ Mapping file not found: {mapping_file}")
        return 1
    
    print(f"🔧 Refactoring {handler_file.name}...")
    print(f"📋 Using mapping: {mapping_file.name}")
    print()
    
    refactorer = HandlerRefactorer(handler_file, mapping_file)
    
    if refactorer.refactor():
        refactorer.save(backup=not args.no_backup)
        print("\n✅ Refactoring complete!")
        return 0
    else:
        print("\n⚠️  No changes made")
        return 0


if __name__ == '__main__':
    exit(main())

