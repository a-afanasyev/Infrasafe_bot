#!/usr/bin/env python3
"""
Скрипт для автоматического исправления обработчиков в user_management.py
"""

import re

def fix_user_management_handlers():
    """Исправляем обработчики в user_management.py"""
    
    # Читаем файл
    with open('uk_management_bot/handlers/user_management.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерны для замены
    patterns = [
        # Исправляем сигнатуры функций
        (
            r'async def (\w+)\(callback: CallbackQuery, db: Session, roles: list = None\):',
            r'async def \1(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):'
        ),
        (
            r'async def (\w+)\(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None\):',
            r'async def \1(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None):'
        ),
        # Исправляем старые проверки прав доступа
        (
            r'# Проверяем права доступа\n\s+if not roles or not any\(role in \[\'admin\', \'manager\'\] for role in roles\):',
            r'# Проверяем права доступа через утилитарную функцию\n    has_access = has_admin_access(roles=roles, user=user)\n    \n    if not has_access:'
        ),
        # Исправляем вызовы show_user_management_panel
        (
            r'await show_user_management_panel\(callback, db, roles\)',
            r'await show_user_management_panel(callback, db, roles, active_role, user)'
        ),
    ]
    
    # Применяем замены
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    # Записываем обратно
    with open('uk_management_bot/handlers/user_management.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Обработчики в user_management.py исправлены")

if __name__ == "__main__":
    fix_user_management_handlers()
