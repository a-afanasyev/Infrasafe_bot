#!/usr/bin/env python3
"""
Advanced Handler Refactorer - TASK 17 Phase 2
Улучшенная версия скрипта рефакторинга с использованием AST для точного парсинга.

Использование:
    python scripts/refactor_handler_advanced.py --file handlers/requests.py --mapping mappings/handlers_mapping.json
"""

import json
import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import shutil


class AdvancedHandlerRefactorer:
    """Продвинутый рефакторинг handler файлов с использованием AST."""
    
    def __init__(self, handler_file: Path, mapping_file: Path):
        self.handler_file = handler_file
        self.mapping_file = mapping_file
        
        # Загружаем mapping
        with open(mapping_file, 'r', encoding='utf-8') as f:
            self.mapping_data = json.load(f)
        
        # Группируем по файлам и строкам
        self.file_mappings = {}
        for item in self.mapping_data:
            source = item.get('source', '')
            if handler_file.name in source:
                line_num = self._extract_line_number(source)
                if line_num:
                    self.file_mappings[line_num] = {
                        'key': item['key'],
                        'ru_text': item.get('ru_text', ''),
                        'context': item.get('context', '')
                    }
        
        # Читаем исходный файл
        with open(handler_file, 'r', encoding='utf-8') as f:
            self.content = f.read()
            self.lines = self.content.split('\n')
        
        self.changes_made = []
        self.imports_added = set()
        
        # Парсим AST
        try:
            self.tree = ast.parse(self.content)
        except SyntaxError as e:
            print(f"⚠️  Syntax error in {handler_file.name}: {e}")
            self.tree = None
    
    def _extract_line_number(self, source: str) -> Optional[int]:
        """Извлекает номер строки из source."""
        match = re.search(r':(\d+)$', source)
        return int(match.group(1)) if match else None
    
    def add_imports(self):
        """Добавляет необходимые импорты."""
        imports_to_add = {
            'get_text': 'from uk_management_bot.utils.helpers import get_text',
            'get_language': 'from uk_management_bot.utils.language_helpers import get_language_for_user'
        }
        
        # Проверяем какие импорты уже есть
        has_get_text = 'from uk_management_bot.utils.helpers import get_text' in self.content
        has_get_language = 'from uk_management_bot.utils.language_helpers import get_language_for_user' in self.content
        
        if has_get_text and has_get_language:
            return
        
        # Находим место для вставки импортов
        import_pattern = re.compile(r'^(from|import) ')
        last_import_line = -1
        
        for i, line in enumerate(self.lines):
            if import_pattern.match(line.strip()):
                last_import_line = i
        
        insert_line = last_import_line + 1 if last_import_line >= 0 else 0
        
        # Добавляем импорты
        lines_to_insert = []
        if not has_get_text:
            lines_to_insert.append(imports_to_add['get_text'])
            self.imports_added.add('get_text')
        if not has_get_language:
            lines_to_insert.append(imports_to_add['get_language'])
            self.imports_added.add('get_language_for_user')
        
        if lines_to_insert:
            # Добавляем пустую строку если нужно
            if insert_line < len(self.lines) and self.lines[insert_line].strip():
                lines_to_insert.insert(0, '')
            
            self.lines.insert(insert_line, '\n'.join(lines_to_insert))
            self.changes_made.append(f"Added imports: {', '.join(lines_to_insert)}")
    
    def find_and_replace_strings(self):
        """Находит и заменяет хардкодные строки."""
        replacements = []
        
        # Собираем все замены
        for line_num, mapping_info in self.file_mappings.items():
            if line_num >= len(self.lines):
                continue
            
            ru_text = mapping_info['ru_text']
            locale_key = mapping_info['key']
            
            # Ищем строку в файле (может быть многострочной)
            line_idx = line_num - 1  # 0-based
            
            # Проверяем текущую строку
            if line_idx < len(self.lines):
                line = self.lines[line_idx]
                
                # Ищем различные паттерны
                # Паттерн 1: Простая строка в кавычках
                if ru_text in line:
                    # Находим точное местоположение строки
                    if f'"{ru_text}"' in line:
                        old_expr = f'"{ru_text}"'
                        replacements.append((line_idx, old_expr, locale_key, 'simple'))
                    elif f"'{ru_text}'" in line:
                        old_expr = f"'{ru_text}'"
                        replacements.append((line_idx, old_expr, locale_key, 'simple'))
                    # Многострочная строка
                    elif ru_text[:50] in line:
                        # Это может быть многострочная строка
                        replacements.append((line_idx, ru_text[:50], locale_key, 'multiline'))
        
        return replacements
    
    def ensure_language_in_function(self, func_start_line: int):
        """Проверяет и добавляет получение языка в функцию."""
        # Ищем сигнатуру функции
        func_pattern = re.compile(r'^\s*(async\s+)?def\s+\w+\s*\(')
        
        # Находим начало функции
        func_line_idx = func_start_line - 1 if func_start_line > 0 else 0
        
        if func_line_idx >= len(self.lines):
            return False
        
        func_line = self.lines[func_line_idx]
        
        if not func_pattern.match(func_line):
            return False
        
        # Проверяем есть ли уже language в функции
        if 'language' in func_line.lower() or 'lang' in func_line.lower():
            # Проверяем используется ли он
            in_func_body = False
            has_lang_var = False
            
            for i in range(func_line_idx, min(func_line_idx + 100, len(self.lines))):
                line = self.lines[i]
                
                # Определяем начало тела функции
                if ':' in line and func_pattern.match(self.lines[i-1] if i > 0 else ''):
                    in_func_body = True
                
                if in_func_body:
                    if 'lang' in line or 'language' in line:
                        has_lang_var = True
                        break
                    
                    # Проверяем отступы - если отступ меньше чем у функции, значит мы вышли
                    if line.strip() and not line.strip().startswith('#'):
                        current_indent = len(line) - len(line.lstrip())
                        func_indent = len(func_line) - len(func_line.lstrip())
                        if current_indent <= func_indent:
                            break
            
            if has_lang_var:
                return True  # Уже есть язык
        
        # Определяем тип функции (message или callback)
        has_message = 'message' in func_line.lower() or 'Message' in func_line
        has_callback = 'callback' in func_line.lower() or 'CallbackQuery' in func_line
        has_db = 'db' in func_line.lower() or 'session' in func_line.lower()
        
        if not has_db:
            return False  # Не можем получить язык без db
        
        # Находим начало тела функции
        body_start_idx = func_line_idx + 1
        for i in range(func_line_idx, min(func_line_idx + 10, len(self.lines))):
            if ':' in self.lines[i] and i > func_line_idx:
                body_start_idx = i + 1
                break
        
        # Определяем отступ
        indent = len(self.lines[body_start_idx]) - len(self.lines[body_start_idx].lstrip()) if body_start_idx < len(self.lines) else 4
        
        # Генерируем код получения языка
        if has_message and has_db:
            lang_code = f"{' ' * indent}lang = await get_language_for_user(message.from_user.id, db, message)"
        elif has_callback and has_db:
            lang_code = f"{' ' * indent}lang = await get_language_for_user(callback.from_user.id, db, callback)"
        else:
            return False  # Не знаем как получить
        
        # Вставляем код
        self.lines.insert(body_start_idx, lang_code)
        self.changes_made.append(f"Added language detection in function at line {func_line_idx + 1}")
        
        return True
    
    def replace_string_in_line(self, line_idx: int, old_expr: str, locale_key: str, replace_type: str):
        """Заменяет строку в строке файла."""
        if line_idx >= len(self.lines):
            return False
        
        line = self.lines[line_idx]
        
        # Проверяем контекст использования
        # Если это await message.answer(...) или await callback.answer(...)
        if 'await' in line and ('answer' in line or 'edit_text' in line or 'reply' in line):
            # Заменяем строку на get_text вызов
            new_expr = f'get_text("{locale_key}", language=lang)'
            
            # Простая замена
            if replace_type == 'simple':
                # Находим строку в кавычках
                if old_expr in line:
                    line = line.replace(old_expr, new_expr)
                    self.lines[line_idx] = line
                    self.changes_made.append(f"Line {line_idx + 1}: replaced '{old_expr[:50]}...' with get_text('{locale_key}')")
                    return True
            elif replace_type == 'multiline':
                # Для многострочных строк нужна более сложная логика
                # Пока просто заменяем начало
                if old_expr in line:
                    # Находим начало строки
                    pattern = re.escape(old_expr[:30])
                    line = re.sub(pattern, new_expr, line, count=1)
                    self.lines[line_idx] = line
                    self.changes_made.append(f"Line {line_idx + 1}: replaced multiline string with get_text('{locale_key}')")
                    return True
        
        return False
    
    def refactor(self) -> bool:
        """Выполняет рефакторинг."""
        if not self.file_mappings:
            print(f"⚠️  No mappings found for {self.handler_file.name}")
            return False
        
        # Добавляем импорты
        self.add_imports()
        
        # Находим замены
        replacements = self.find_and_replace_strings()
        
        if not replacements:
            print(f"⚠️  No string replacements found for {self.handler_file.name}")
            print(f"   Found {len(self.file_mappings)} mappings but couldn't match strings")
            return False
        
        # Группируем замены по функциям
        func_replacements = defaultdict(list)
        for line_idx, old_expr, locale_key, replace_type in replacements:
            # Находим функцию для этой строки
            func_start = self._find_function_start(line_idx)
            if func_start:
                func_replacements[func_start].append((line_idx, old_expr, locale_key, replace_type))
        
        # Для каждой функции добавляем language если нужно
        for func_start in func_replacements.keys():
            self.ensure_language_in_function(func_start)
        
        # Выполняем замены (в обратном порядке)
        for line_idx, old_expr, locale_key, replace_type in reversed(replacements):
            self.replace_string_in_line(line_idx, old_expr, locale_key, replace_type)
        
        return len(self.changes_made) > 0
    
    def _find_function_start(self, line_idx: int) -> Optional[int]:
        """Находит начало функции для данной строки."""
        func_pattern = re.compile(r'^\s*(async\s+)?def\s+\w+\s*\(')
        
        # Ищем вверх от текущей строки
        for i in range(line_idx, -1, -1):
            if i < len(self.lines) and func_pattern.match(self.lines[i]):
                return i + 1  # 1-based line number
        
        return None
    
    def save(self, backup: bool = True):
        """Сохраняет изменения."""
        if backup:
            backup_path = self.handler_file.with_suffix(f'.{self.handler_file.suffix}.backup_refactor')
            shutil.copy2(self.handler_file, backup_path)
            print(f"📦 Backup created: {backup_path}")
        
        # Сохраняем файл
        new_content = '\n'.join(self.lines)
        with open(self.handler_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"💾 Saved: {self.handler_file}")
        print(f"✅ Made {len(self.changes_made)} changes")
        for change in self.changes_made[:15]:  # Показываем первые 15
            print(f"   - {change}")
        if len(self.changes_made) > 15:
            print(f"   ... and {len(self.changes_made) - 15} more")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Advanced refactor handler files for localization")
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
    
    print(f"🔧 Advanced Refactoring {handler_file.name}...")
    print(f"📋 Using mapping: {mapping_file.name}")
    print(f"📊 Found {len([m for m in json.load(open(mapping_file)) if handler_file.name in m.get('source', '')])} mappings for this file")
    print()
    
    refactorer = AdvancedHandlerRefactorer(handler_file, mapping_file)
    
    if refactorer.refactor():
        refactorer.save(backup=not args.no_backup)
        print("\n✅ Refactoring complete!")
        return 0
    else:
        print("\n⚠️  No changes made")
        return 0


if __name__ == '__main__':
    exit(main())

