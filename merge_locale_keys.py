#!/usr/bin/env python3
"""
Скрипт для объединения новых ключей локализации с основным файлом
"""
import json
import os

def merge_locale_keys(main_file_path, new_keys_file_path, output_file_path=None):
    """
    Объединяет основные ключи локализации с новыми ключами
    
    Args:
        main_file_path: Путь к основному файлу локализации
        new_keys_file_path: Путь к файлу с новыми ключами
        output_file_path: Путь к выходному файлу (если None, перезаписывает основной)
    """
    # Загружаем основной файл
    with open(main_file_path, 'r', encoding='utf-8') as f:
        main_data = json.load(f)
    
    # Загружаем новые ключи
    with open(new_keys_file_path, 'r', encoding='utf-8') as f:
        new_data = json.load(f)
    
    # Объединяем ключи
    for section, keys in new_data.items():
        if section not in main_data:
            main_data[section] = {}
        
        # Обновляем существующие или добавляем новые ключи
        main_data[section].update(keys)
    
    # Сохраняем результат
    output_path = output_file_path or main_file_path
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)
    
    print(f"Ключи успешно объединены в файл: {output_path}")

if __name__ == "__main__":
    # Пути к файлам
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ru_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/ru.json")
    ru_new_keys_path = os.path.join(base_dir, "uk_management_bot/config/locales/ru_new_keys.json")
    uz_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/uz.json")
    uz_new_keys_path = os.path.join(base_dir, "uk_management_bot/config/locales/uz_new_keys.json")
    
    # Объединяем ключи для русского языка
    merge_locale_keys(ru_main_path, ru_new_keys_path)
    
    # Объединяем ключи для узбекского языка
    merge_locale_keys(uz_main_path, uz_new_keys_path)
    
    print("Объединение ключей локализации завершено!")
