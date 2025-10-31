#!/usr/bin/env python3
"""
Скрипт для поиска и перевода русских строк в uz.json
Находит все значения с кириллицей и переводит их на узбекский язык
"""

import json
import re
import argparse
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
import logging

# Попытка импортировать googletrans
try:
    from googletrans import Translator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    Translator = None  # Для типизации

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Регулярное выражение для поиска кириллицы
CYRILLIC_PATTERN = re.compile(r'[\u0400-\u04FF]')


def has_cyrillic(text: str) -> bool:
    """
    Проверяет, содержит ли текст кириллицу
    
    Args:
        text: Строка для проверки
        
    Returns:
        True если содержит кириллицу, False иначе
    """
    if not isinstance(text, str):
        return False
    return bool(CYRILLIC_PATTERN.search(text))


def flatten_dict(d: Dict[str, Any], parent_key: str = '', separator: str = '.') -> Dict[str, str]:
    """
    Преобразует вложенный словарь в плоский словарь с точечной нотацией
    
    Args:
        d: Вложенный словарь
        parent_key: Родительский ключ (для рекурсии)
        separator: Разделитель между ключами
        
    Returns:
        Плоский словарь с точечной нотацией
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{separator}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, separator).items())
        else:
            items.append((new_key, str(v) if v is not None else ""))
    return dict(items)


def unflatten_dict(flat_dict: Dict[str, str], separator: str = '.') -> Dict[str, Any]:
    """
    Преобразует плоский словарь обратно во вложенный
    
    Args:
        flat_dict: Плоский словарь с точечной нотацией
        separator: Разделитель между ключами
        
    Returns:
        Вложенный словарь
    """
    result = {}
    for key, value in flat_dict.items():
        parts = key.split(separator)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result


def find_russian_values(uz_locale: Dict[str, Any], ru_locale: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Находит все значения с кириллицей в uz.json и их русские эквиваленты
    
    Args:
        uz_locale: Узбекский словарь локализации
        ru_locale: Русский словарь локализации
        
    Returns:
        Список кортежей (ключ, русское_значение, текущее_узбекское_значение)
    """
    uz_flat = flatten_dict(uz_locale)
    ru_flat = flatten_dict(ru_locale)
    
    russian_values = []
    
    for key, uz_value in uz_flat.items():
        # Пропускаем, если значение уже переведено или это [TRANSLATE] маркер
        if uz_value == "[TRANSLATE]" or not has_cyrillic(uz_value):
            continue
            
        # Проверяем, содержит ли значение кириллицу
        if has_cyrillic(uz_value):
            # Получаем русское значение для перевода
            ru_value = ru_flat.get(key, uz_value)
            russian_values.append((key, ru_value, uz_value))
    
    return russian_values


def translate_text(text: str, translator, src: str = 'ru', dest: str = 'uz') -> str:
    """
    Переводит текст с русского на узбекский
    
    Args:
        text: Текст для перевода
        translator: Переводчик Google Translate
        src: Исходный язык
        dest: Целевой язык
        
    Returns:
        Переведенный текст или оригинал при ошибке
    """
    if not text or not text.strip():
        return text
    
    try:
        result = translator.translate(text, src=src, dest=dest)
        return result.text
    except Exception as e:
        logger.error(f"❌ Ошибка перевода: {text[:50]}... - {e}")
        return text  # Возвращаем оригинал при ошибке


def main():
    parser = argparse.ArgumentParser(
        description="Находит и переводит русские строки в uz.json"
    )
    parser.add_argument(
        '--ru-locale',
        default='uk_management_bot/config/locales/ru.json',
        help='Путь к ru.json'
    )
    parser.add_argument(
        '--uz-locale',
        default='uk_management_bot/config/locales/uz.json',
        help='Путь к uz.json'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Тестовый прогон без изменения файлов'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Размер батча для перевода'
    )

    args = parser.parse_args()

    print("🔍 Поиск русских строк в uz.json")
    print("=" * 80)

    # Для dry-run переводчик не нужен
    if not args.dry_run and not TRANSLATOR_AVAILABLE:
        print("❌ ОШИБКА: библиотека googletrans не установлена")
        print("   Установите: pip install googletrans==4.0.0-rc1")
        return 1

    # Загружаем файлы локализации
    ru_locale_path = Path(args.ru_locale)
    uz_locale_path = Path(args.uz_locale)

    if not ru_locale_path.exists():
        print(f"❌ ОШИБКА: {ru_locale_path} не найден")
        return 1

    if not uz_locale_path.exists():
        print(f"❌ ОШИБКА: {uz_locale_path} не найден")
        return 1

    print(f"📖 Загрузка файлов локализации...")
    with open(ru_locale_path, 'r', encoding='utf-8') as f:
        ru_locale = json.load(f)

    with open(uz_locale_path, 'r', encoding='utf-8') as f:
        uz_locale = json.load(f)

    # Находим русские значения
    print(f"🔍 Поиск значений с кириллицей...")
    russian_values = find_russian_values(uz_locale, ru_locale)

    if not russian_values:
        print("✅ Русских строк не найдено! Все значения переведены.")
        return 0

    print(f"📝 Найдено {len(russian_values)} значений с кириллицей")
    print()

    # Показываем первые 10 примеров
    print("Примеры найденных русских строк:")
    for i, (key, ru_value, uz_value) in enumerate(russian_values[:10], 1):
        print(f"  {i}. {key}")
        print(f"     RU: {ru_value[:80]}...")
        print(f"     UZ (текущее): {uz_value[:80]}...")
        print()

    if len(russian_values) > 10:
        print(f"  ... и еще {len(russian_values) - 10} строк")
        print()

    if args.dry_run:
        print("🔍 ТЕСТОВЫЙ ПРОГОН - файлы не будут изменены")
        return 0

    # Подтверждение
    response = input(f"\n❓ Перевести {len(russian_values)} строк? (yes/no): ")
    if response.lower() not in ['yes', 'y', 'да', 'д']:
        print("Отменено пользователем")
        return 0

    # Создаем переводчик
    translator = Translator()

    # Создаем бэкап
    backup_path = uz_locale_path.with_suffix('.json.backup_russian_fix')
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale, f, ensure_ascii=False, indent=2)
    print(f"📦 Бэкап создан: {backup_path}")

    # Переводим в батчах
    print(f"\n🌐 Начало перевода (размер батча: {args.batch_size})...")
    print(f"⏱️  Примерное время: {len(russian_values) * 0.5 / 60:.1f} минут")
    print()

    uz_flat = flatten_dict(uz_locale)
    translated_count = 0
    error_count = 0

    for i in range(0, len(russian_values), args.batch_size):
        batch = russian_values[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(russian_values) + args.batch_size - 1) // args.batch_size

        print(f"📦 Батч {batch_num}/{total_batches} ({len(batch)} строк)")

        for key, ru_value, uz_value in batch:
            try:
                # Переводим русское значение
                translated = translate_text(ru_value, translator, src='ru', dest='uz')
                
                if translated != ru_value:  # Если перевод успешен
                    uz_flat[key] = translated
                    translated_count += 1
                    logger.info(f"✅ {key}: {ru_value[:50]}... → {translated[:50]}...")
                else:
                    error_count += 1
                    logger.warning(f"⚠️  {key}: перевод не выполнен, оставлено оригинальное значение")
                
                # Задержка для избежания блокировки API
                time.sleep(0.5)
                
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка перевода {key}: {e}")

        print(f"   ✅ Обработано {translated_count}/{len(russian_values)}")
        print()

    # Сохраняем обновленный файл
    print(f"💾 Сохранение переводов в {uz_locale_path}...")
    uz_locale_updated = unflatten_dict(uz_flat)
    
    with open(uz_locale_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale_updated, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("ИТОГИ ПЕРЕВОДА")
    print("=" * 80)
    print(f"✅ Переведено: {translated_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"📊 Всего обработано: {len(russian_values)}")
    print(f"💾 Файл обновлен: {uz_locale_path}")
    print(f"📦 Бэкап: {backup_path}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    exit(main())

