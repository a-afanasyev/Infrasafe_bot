#!/usr/bin/env python3
"""
Скрипт для объединения дополнительных ключей локализации
"""
import json
import os

def merge_additional_keys():
    """Объединяет дополнительные ключи локализации с основными файлами"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Пути к файлам
    ru_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/ru.json")
    ru_additional_path = os.path.join(base_dir, "uk_management_bot/config/locales/ru_additional_keys.json")
    uz_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/uz.json")
    
    # Загружаем основные файлы
    with open(ru_main_path, 'r', encoding='utf-8') as f:
        ru_data = json.load(f)
    
    with open(uz_main_path, 'r', encoding='utf-8') as f:
        uz_data = json.load(f)
    
    # Загружаем дополнительные ключи для русского языка
    with open(ru_additional_path, 'r', encoding='utf-8') as f:
        ru_additional = json.load(f)
    
    # Объединяем ключи для русского языка
    for section, keys in ru_additional.items():
        if section not in ru_data:
            ru_data[section] = {}
        ru_data[section].update(keys)
    
    # Создаем узбекские ключи на основе русских
    uz_additional = {}
    for section, keys in ru_additional.items():
        if section not in uz_data:
            uz_additional[section] = {}
        
        # Создаем узбекские переводы (здесь должны быть реальные переводы)
        if section == "buttons":
            uz_additional[section] = {
                "add_apartment": "➕ Kvartira qo'shish",
                "search_apartment": "🔍 Kvartirani qidirish",
                "back_to_menu": "◀️ Orqaga",
                "back_to_selection": "◀️ Tanlovga qaytish",
                "all_selected": "✅ Barchasi tanlandi",
                "clear": "❌ Tozalash",
                "select_all": "🔘 Barchasini tanlang",
                "create_plan": "✅ Reja tuzish",
                "additional_settings": "⚙️ Qo'shimcha sozlamalar",
                "preview": "📋 Oldindan ko'rish",
                "coverage_247": "🌙 24/7 qoplam",
                "balance_load": "⚖️ Yuklanishni muvozanlashtirish",
                "edit_specializations": "✏️ Ixtisosliklarni o'zgartirish",
                "change_period": "📅 Davrni o'zgartirish",
                "detailed_stats": "📊 Batafsiyat statistika",
                "export_schedule": "📋 Jadvalni eksport qilish",
                "notify_employees": "👥 Xodimlarni ogohlantirish",
                "resolve_conflicts": "⚠️ Ziddliklarni hal qilish",
                "edit_plan": "✏️ Rejani tahrirlash",
                "recalculate": "🔄 Qayta hisoblash",
                "create_new_plan": "📅 Yangi reja tuzish",
                "analytics": "📈 Analitika",
                "main_menu": "🏠 Asosiy menyu",
                "active_transfers": "🔄 Faol o'tkazmalar",
                "pending_transfers": "⏳ Kutayotgan o'tkazmalar",
                "transfer_history": "✅ O'tkazmalar tarixi",
                "initiate_transfer": "➕ O'tkazmani boshlash",
                "search_transfers": "🔍 O'tkazmalarni qidirishi",
                "efficiency": "📊 Rejalarning samaradorligi",
                "workload": "👥 Xodimchilarning yuklamasi",
                "coverage": "🎯 Ixtisosliklarni qoplam",
                "timing_metrics": "⏱️ Vaqt ko'rsatkichlari",
                "recommendations": "💡 Tavsiyalar",
                "export_report": "📈 Hisobotni eksport qilish",
                "back": "🔙 Orqaga",
                "view_media": "📎 Mediani ko'rish",
                "assign_request": "📝 Arizani tayinlash",
                "view_assignments": "👥 Tayinlovlar ko'rish",
                "add_comment": "📝 Izoh qo'shish",
                "change_status": "🔄 Holatni o'zgartirish",
                "my_requests": "📋 Mening arizalarim",
                "statistics": "📊 Statistika",
                "back_to_requests": "🔙 Arizalarga qaytish",
                "purchase_materials": "🛒 Materiallarni sotib olish",
                "request_clarification": "❓ Aniqlash so'rovi",
                "complete_work": "✅ Ishni tugatish",
                "return_to_work": "🔄 Ishga qaytish",
                "yes_complete": "✅ Ha, tugatish",
                "cancel": "❌ Bekor qilish",
                "confirm_assignment": "📋 Arizani tayinlash",
                "view_comments": "📋 Izohlarni ko'rish",
                "media": "📎 Media",
                "phone_required": "📱 Telefon raqamini",
                "upload_documents": "📄 Hujjatlar yuklash",
                "complete_without_docs": "✅ Hujjatsiz tugatish"
            }
        elif section == "validation":
            uz_additional[section] = {
                "description_empty": "Tavsif bo'sh bo'lishi mumkin emas",
                "description_too_short": "Tavsif kamida 10 ta belgidan iborat bo'lishi kerak",
                "description_too_long": "Tavsif juday uzun (maksimum {MAX_DESCRIPTION_LENGTH} belgi)",
                "description_correct": "Tavsif to'g'ri",
                "apartment_optional": "Kvartira raqami ixtiyori emas",
                "apartment_too_long": "Kvartira raqami juday uzun (maksimum {MAX_APARTMENT_LENGTH} belgi)",
                "apartment_invalid_chars": "Kvartira raqami faqat raqamlar, harflar va defisni o'z ichi mumkin",
                "apartment_correct": "Kvartira raqami to'g'ri",
                "category_empty": "Kategoriya bo'sh bo'lishi mumkin emas",
                "invalid_category": "Noto'g'ri kategoriya. Mavjud kategoriyalar: {categories_list}",
                "category_correct": "Kategoriya to'g'ri",
                "status_empty": "Holat bo'sh bo'lishi mumkin emas",
                "invalid_status": "Noto'g'ri holat: {new_status}",
                "completed": "Bajarilgan",
                "in_work": "Ishda",
                "purchase": "Sotib olish",
                "clarification": "Aniqlash",
                "cancelled": "Bekor qilindi",
                "accepted": "Qabul qilindi",
                "in_progress": "Bajarilmoqda",
                "phone_empty": "Telefon raqami bo'sh bo'lishi mumkin emas",
                "phone_valid": "Telefon raqami to'g'ri",
                "phone_invalid_format": "Telefon raqami noto'g'ri formati",
                "address_empty": "Manzil bo'sh bo'lishi mumkin emas",
                "description_too_short_or_long": "Tavsif juday qisqa yoki juday uzun",
                "new": "Yangi",
                "invalid_category_key": "Noto'g'ri kategoriya: {category} (kalitda {category_key} da hal qilingan)",
                "invalid_urgency": "Noto'g'ri shoshilinchlik: {urgency}",
                "user_by_telegram_id": "Telegram ID bo'yicha foydalanuvchini olish",
                "added_statuses": "\"Bajarilgan\" va \"Qabul qilingan\" statuslari qo'shildi",
                "removed_status": "\"Tasdiqlangan\" eski status o'chirildi",
                "status_transitions": {
                    "Yangi": ["Ishda", "Sotib olish", "Aniqlash", "Bekor qilindi"],
                    "Ishda": ["Aniqlash", "Sotib olish", "Bajarilgan", "Bekor qilindi"],
                    "Aniqlash": ["Ishda", "Sotib olish", "Bajarilgan", "Bekor qilindi"],
                    "Sotib olish": ["Ishda", "Aniqlash", "Bajarilgan", "Bekor qilindi"],
                    "Bajarilgan": ["Qabul qilingan", "Ishda", "Aniqlash", "Bekor qilindi"],
                    "Qabul qilingan": [],
                    "Bekor qilindi": []
                }
            }
    
    # Сохраняем обновленные файлы
    with open(ru_main_path, 'w', encoding='utf-8') as f:
        json.dump(ru_data, f, ensure_ascii=False, indent=2)
    
    with open(uz_main_path, 'w', encoding='utf-8') as f:
        json.dump(uz_data, f, ensure_ascii=False, indent=2)
    
    print("Дополнительные ключи локализации успешно объединены!")

if __name__ == "__main__":
    merge_additional_keys()

