"""
Тестовый скрипт для проверки функционала управления дворами пользователей
"""
import sys
sys.path.insert(0, '/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK')

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.database.models import User, Yard, UserYard
from uk_management_bot.services.address_service import AddressService
from sqlalchemy import func

def test_user_yards():
    """Тестируем функционал дополнительных дворов"""
    db = SessionLocal()

    try:
        print("=" * 60)
        print("ТЕСТИРОВАНИЕ ФУНКЦИОНАЛА УПРАВЛЕНИЯ ДВОРАМИ ПОЛЬЗОВАТЕЛЕЙ")
        print("=" * 60)

        # 1. Проверяем пользователей с ролью applicant
        print("\n1. Проверка пользователей с ролью 'applicant':")
        users = db.query(User).filter(
            User.status == 'approved'
        ).all()

        applicant_users = []
        for u in users:
            is_applicant = False

            # Проверяем через roles (JSON)
            if u.roles:
                import json
                try:
                    parsed_roles = json.loads(u.roles)
                    if isinstance(parsed_roles, list) and 'applicant' in parsed_roles:
                        is_applicant = True
                except:
                    pass

            # Проверяем через active_role
            if not is_applicant and u.active_role == 'applicant':
                is_applicant = True

            if is_applicant:
                applicant_users.append(u)
                print(f"   ✓ {u.first_name or 'Unnamed'} (ID: {u.telegram_id}, roles: {u.roles}, active_role: {u.active_role})")

        print(f"\n   Всего жителей (applicant): {len(applicant_users)}")

        if not applicant_users:
            print("   ⚠️  Нет пользователей с ролью applicant!")
            return

        # 2. Проверяем доступные дворы
        print("\n2. Проверка дворов в системе:")
        yards = db.query(Yard).filter(Yard.is_active == True).all()
        print(f"   Всего активных дворов: {len(yards)}")
        for yard in yards[:5]:  # Показываем первые 5
            print(f"   • {yard.name} (ID: {yard.id})")

        # 3. Проверяем существующие связи UserYard
        print("\n3. Проверка существующих дополнительных дворов:")
        user_yards = db.query(UserYard).all()
        print(f"   Всего записей UserYard: {len(user_yards)}")
        for uy in user_yards:
            user = db.query(User).filter(User.id == uy.user_id).first()
            yard = db.query(Yard).filter(Yard.id == uy.yard_id).first()
            print(f"   • {user.first_name if user else 'Unknown'} → {yard.name if yard else 'Unknown'}")

        # 4. Тестируем метод get_user_available_yards для первого жителя
        if applicant_users:
            test_user = applicant_users[0]
            print(f"\n4. Тестирование get_user_available_yards для пользователя {test_user.first_name}:")

            available_yards = AddressService.get_user_available_yards(db, test_user.telegram_id)
            print(f"   Доступно дворов: {len(available_yards)}")
            for yard in available_yards:
                print(f"   • {yard.name}")

        # 5. Проверяем таблицу user_yards
        print("\n5. Проверка структуры таблицы user_yards:")
        result = db.execute("SELECT COUNT(*) FROM user_yards")
        count = result.scalar()
        print(f"   Записей в таблице: {count}")

        print("\n" + "=" * 60)
        print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    test_user_yards()
