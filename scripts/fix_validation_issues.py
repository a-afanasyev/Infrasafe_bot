#!/usr/bin/env python3
"""
Исправляет format mismatches в uz.json, заменяя параметры на правильные из ru.json.
"""

import json
import re
from pathlib import Path

def flatten_keys(nested_dict, prefix=''):
    """Flatten nested locale dictionary."""
    flat = {}
    for key, value in nested_dict.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_keys(value, full_key))
        else:
            flat[full_key] = value
    return flat

def unflatten_keys(flat_dict):
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

def get_nested(d, key):
    """Get nested value."""
    parts = key.split('.')
    val = d
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, {})
        else:
            return None
    return val if isinstance(val, str) else None

def set_nested(d, key, value):
    """Set nested value."""
    parts = key.split('.')
    current = d
    for i, part in enumerate(parts[:-1]):
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value

def fix_format_mismatches(ru_locale, uz_locale):
    """Fix format mismatches in uz.json."""
    
    # Маппинг проблемных параметров
    fixes = {
        'comments.success': {
            'uz_current': "④ Shrift # {so'rov_number} so'roviga muvaffaqiyatli qo'shildi",
            'uz_fixed': "✅ Kommentariya #{request_number} so'roviga muvaffaqiyatli qo'shildi",
            'params': ['request_number']
        },
        'invites.link_generated': {
            'uz_current': None,  # Будет заменено полностью
            'uz_fixed': "✅ Taklif yaratildi!\n\n🔗 Ro'yxatdan o'tish havolasi:\n`{link}`\n\n📋 Nomzod uchun ko'rsatmalar:\n1. Havolaga amal qiling\n2. \"Boshlash\" tugmasini bosing\n3. buyruqni yuboring: `/join {token}`\n\nAmal qilish muddati: {expires}",
            'params': ['expires', 'link', 'token']
        },
        'invites.registration_started': {
            'uz_current': None,
            'uz_fixed': "🎯 Ro'yxatdan o'tishni boshlaylik!\n\n👤 Rol: {role}\n\n🌐 Ro'yxatdan o'tish shaklini ochish va ma'lumotlarni to'ldirish uchun quyidagi tugmani bosing.",
            'params': ['role']
        },
        'invites.web_registration_info': {
            'uz_current': None,
            'uz_fixed': "🎯 Ro'yxatdan o'tishga taklif\n\n👤 Rol: {role}\n🌐 Ro'yxatdan o'tish shakli: {url}\n\n📋 Ro'yxatdan o'tishni tugatish:\n1. \"Ochiq ro'yxatga olish shakli\" tugmasini bosing\n2. Internetdagi ma'lumotlarni to'ldiring\n3. Telegram orqali tizimga kiring\n4. Administratorni ma'qullash uchun kuting",
            'params': ['role', 'url']
        },
        'invites.web_registration_instructions': {
            'uz_current': None,
            'uz_fixed': "📋 Ro'yxatdan o'tish uchun batafsil ko'rsatmalar\n\n🌐 ** Veb-ro'yxatga olish shakli: **\n{url}\n\n📝 ** bosqichma-bosqich ko'rsatmalar: **\n\n1️⃣ ** Ro'yxatdan o'tish formasini oching **\n• \"Ochiq ro'yxatga olish shakli\" tugmasini bosing\n• yoki havolani qo'lda kuzatib boring\n\n2️⃣ ** Tafsilotlarni to'ldiring **\n• To'liq ismingizni kiriting (to'liq ism)\n• Agar siz ijrochi bo'lsangiz, ixtisoslikni tanlang\n• Ma'lumot to'g'ri ekanligini tekshiring\n\n3️⃣ ** Telegram ** orqali tizimga kiring\n• \"Telegram orqali kirish\" tugmasini bosing\n• Telegramda avtorizatsiya tasdiqlang\n• Tasdiqlashni kuting\n\n4️⃣ ** Ro'yxatdan o'tish **\n• \"To'liq ro'yxatga olish\" tugmasini bosing\n• Tasdiqlashni kuting\n• Administratorni tasdiqlash uchun kuting\n\n✅ ** Tasdiqlangandan keyin siz bildirishnomani olasiz va tizimdan foydalanishingiz mumkin **",
            'params': ['url']
        },
        'moderation.enter_document_request_multiple': {
            'uz_current': "④ Hujjatlar uchun so'rovni kiriting: {Hujjatlar}",
            'uz_fixed': "📋 Hujjatlar uchun so'rovni kiriting: {documents}",
            'params': ['documents']
        },
        'moderation.enter_document_request_specific': {
            'uz_current': "📋 Hujjat uchun so'rovni kiriting: {Hujjat_type}",
            'uz_fixed': "📋 Hujjat uchun so'rovni kiriting: {document_type}",
            'params': ['document_type']
        },
        'shift_management.shifts_not_created_reasons': {
            'uz_current': "Mumkin sabablar:\n• SHIFTS {sana} bo'yicha allaqachon mavjud\n• Hafta kuni shablonga kiritilmagan\n• Hech bir san'atkorlar mavjud emas\n\nShablon sozlamalarini tekshiring va qaytadan urining.",
            'uz_fixed': "Mumkin sabablar:\n• {date} bo'yicha smenalar allaqachon mavjud\n• Hafta kuni shablonga kiritilmagan\n• Hech bir ijrochilar mavjud emas\n\nShablon sozlamalarini tekshiring va qaytadan urining.",
            'params': ['date']
        }
    }
    
    fixed_count = 0
    
    for key, fix_info in fixes.items():
        current_value = get_nested(uz_locale, key)
        if current_value:
            set_nested(uz_locale, key, fix_info['uz_fixed'])
            fixed_count += 1
            print(f"✅ Fixed: {key}")
            print(f"   Old: {current_value[:80]}...")
            print(f"   New: {fix_info['uz_fixed'][:80]}...")
    
    # Удаляем extra key status.accepted из uz.json
    if 'status' in uz_locale and 'accepted' in uz_locale['status']:
        del uz_locale['status']['accepted']
        fixed_count += 1
        print(f"✅ Removed extra key: status.accepted")
    
    return fixed_count

def sort_dict_recursive(d):
    """Sort dictionary recursively."""
    sorted_dict = {}
    for key in sorted(d.keys()):
        if isinstance(d[key], dict):
            sorted_dict[key] = sort_dict_recursive(d[key])
        else:
            sorted_dict[key] = d[key]
    return sorted_dict

def main():
    ru_path = Path('uk_management_bot/config/locales/ru.json')
    uz_path = Path('uk_management_bot/config/locales/uz.json')
    
    # Backup
    backup_path = uz_path.with_suffix('.json.backup_fix')
    with open(uz_path, 'r', encoding='utf-8') as f:
        backup_path.write_text(f.read(), encoding='utf-8')
    print(f"📦 Backup created: {backup_path}")
    
    # Load
    with open(ru_path, 'r', encoding='utf-8') as f:
        ru_locale = json.load(f)
    with open(uz_path, 'r', encoding='utf-8') as f:
        uz_locale = json.load(f)
    
    print("\n🔧 Fixing format mismatches...\n")
    
    # Fix
    fixed_count = fix_format_mismatches(ru_locale, uz_locale)
    
    # Sort
    uz_locale = sort_dict_recursive(uz_locale)
    
    # Save
    with open(uz_path, 'w', encoding='utf-8') as f:
        json.dump(uz_locale, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Fixed {fixed_count} issues")
    print(f"💾 Saved: {uz_path}")

if __name__ == '__main__':
    main()

