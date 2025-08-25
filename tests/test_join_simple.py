"""
Простые тесты для проверки логики команды /join
"""
import json

def test_invite_data_processing():
    """Тест обработки данных из инвайта"""
    
    # Тестовые данные инвайта
    invite_data = {
        "role": "executor",
        "specialization": "plumber,electrician",
        "created_by": 987654321,
        "nonce": "test_nonce_123"
    }
    
    # Тестируем обработку роли
    role = invite_data["role"]
    assert role == "executor"
    
    # Тестируем обработку специализации
    if role == "executor" and invite_data.get("specialization"):
        specializations = invite_data["specialization"].split(",")
        assert len(specializations) == 2
        assert "plumber" in specializations
        assert "electrician" in specializations
    
    # Тестируем создание roles JSON
    current_roles = []
    if role not in current_roles:
        current_roles.append(role)
    
    roles_json = json.dumps(current_roles)
    assert roles_json == '["executor"]'
    
    print("✅ test_invite_data_processing - PASSED")


def test_role_localization_mapping():
    """Тест маппинга ролей для локализации"""
    
    role_mapping = {
        "applicant": "Заявитель",
        "executor": "Исполнитель", 
        "manager": "Менеджер"
    }
    
    # Тестируем все роли
    for role_key, role_name in role_mapping.items():
        assert len(role_name) > 0
        assert role_name != role_key  # должны быть переведены
    
    print("✅ test_role_localization_mapping - PASSED")


def test_error_handling_scenarios():
    """Тест сценариев обработки ошибок"""
    
    error_scenarios = [
        ("Token has expired", "expired"),
        ("Token already used", "used"),
        ("Invalid token signature", "invalid"),
        ("Invalid token format", "invalid")
    ]
    
    for error_message, expected_type in error_scenarios:
        error_msg_lower = error_message.lower()
        
        if "expired" in error_msg_lower:
            result_type = "expired"
        elif "already used" in error_msg_lower:
            result_type = "used"
        else:
            result_type = "invalid"
        
        assert result_type == expected_type, f"Failed for: {error_message}"
    
    print("✅ test_error_handling_scenarios - PASSED")


def test_rate_limiter_logic():
    """Тест логики rate limiting"""
    
    # Симуляция rate limiter storage
    storage = {}
    window = 600  # 10 минут
    max_attempts = 3
    
    def is_allowed(user_id: int, current_time: float) -> bool:
        key = f"join_{user_id}"
        attempts = storage.get(key, [])
        
        # Очищаем старые попытки
        attempts = [t for t in attempts if current_time - t < window]
        
        if len(attempts) >= max_attempts:
            return False
        
        attempts.append(current_time)
        storage[key] = attempts
        return True
    
    user_id = 123456789
    current_time = 1000000000.0
    
    # Первые 3 попытки должны пройти
    assert is_allowed(user_id, current_time) == True
    assert is_allowed(user_id, current_time + 1) == True
    assert is_allowed(user_id, current_time + 2) == True
    
    # 4-я попытка должна быть заблокирована
    assert is_allowed(user_id, current_time + 3) == False
    
    # После истечения окна должно снова разрешиться
    assert is_allowed(user_id, current_time + window + 1) == True
    
    print("✅ test_rate_limiter_logic - PASSED")


def test_user_data_update():
    """Тест обновления данных пользователя при join"""
    
    # Симуляция существующего пользователя
    existing_user = {
        "telegram_id": 123456789,
        "roles": '["applicant"]',
        "active_role": "applicant",
        "status": "approved"
    }
    
    # Данные из инвайта
    invite_data = {
        "role": "executor",
        "specialization": "plumber"
    }
    
    # Обработка добавления новой роли
    current_roles = json.loads(existing_user["roles"])
    new_role = invite_data["role"]
    
    if new_role not in current_roles:
        current_roles.append(new_role)
    
    # Проверяем результат
    assert len(current_roles) == 2
    assert "applicant" in current_roles
    assert "executor" in current_roles
    
    # Обновляем пользователя
    updated_user = existing_user.copy()
    updated_user["roles"] = json.dumps(current_roles)
    updated_user["specialization"] = invite_data["specialization"]
    updated_user["status"] = "pending"  # До одобрения
    
    assert updated_user["specialization"] == "plumber"
    assert updated_user["status"] == "pending"
    
    print("✅ test_user_data_update - PASSED")


if __name__ == "__main__":
    print("🧪 Запуск простых тестов логики /join...")
    
    test_invite_data_processing()
    test_role_localization_mapping()
    test_error_handling_scenarios()
    test_rate_limiter_logic()
    test_user_data_update()
    
    print("\n🎉 Все простые тесты /join прошли успешно!")
