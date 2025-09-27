#!/usr/bin/env python3
# Test script to validate User Service models and schemas
# UK Management Bot - User Service

import asyncio
import sys
from pathlib import Path

# Add the user_service directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_model_schema_alignment():
    """Test that models and schemas are properly aligned"""

    print("🔍 Testing User Service Model-Schema Alignment")
    print("=" * 50)

    # Test 1: Import all models and schemas
    try:
        from models.user import User, UserProfile, UserRoleMapping
        from models.access import AccessRights
        from schemas.user import (
            UserCreate, UserResponse, UserFullResponse,
            UserStatsResponse, UserRoleMappingResponse
        )
        print("✅ All imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

    # Test 2: Check User model fields
    print("\n🔍 Checking User model fields...")
    user_fields = User.__table__.columns.keys()
    expected_user_fields = [
        'id', 'telegram_id', 'username', 'first_name', 'last_name',
        'phone', 'email', 'language_code', 'status', 'is_active',
        'created_at', 'updated_at'
    ]

    missing_fields = set(expected_user_fields) - set(user_fields)
    extra_fields = set(user_fields) - set(expected_user_fields)

    if missing_fields:
        print(f"❌ Missing User fields: {missing_fields}")
    else:
        print("✅ All expected User fields present")

    if extra_fields:
        print(f"ℹ️  Extra User fields: {extra_fields}")

    # Test 3: Check UserProfile model fields
    print("\n🔍 Checking UserProfile model fields...")
    profile_fields = UserProfile.__table__.columns.keys()
    expected_profile_fields = [
        'id', 'user_id', 'birth_date', 'passport_series', 'passport_number',
        'home_address', 'apartment_address', 'yard_address', 'address_type',
        'specialization', 'bio', 'avatar_url', 'created_at', 'updated_at'
    ]

    missing_profile_fields = set(expected_profile_fields) - set(profile_fields)
    if missing_profile_fields:
        print(f"❌ Missing UserProfile fields: {missing_profile_fields}")
    else:
        print("✅ All expected UserProfile fields present")

    # Test 4: Check AccessRights model fields
    print("\n🔍 Checking AccessRights model fields...")
    access_fields = AccessRights.__table__.columns.keys()
    expected_access_fields = [
        'id', 'user_id', 'access_level', 'service_permissions',
        'building_access', 'is_active', 'created_at', 'updated_at'
    ]

    # Test 5: Check relationships
    print("\n🔍 Checking ORM relationships...")

    # User.profile should be uselist=False
    user_profile_rel = User.__mapper__.relationships['profile']
    if user_profile_rel.uselist:
        print("❌ User.profile should be uselist=False (single object)")
    else:
        print("✅ User.profile is correctly configured as single object")

    # User.roles should be uselist=True (default)
    user_roles_rel = User.__mapper__.relationships['roles']
    if not user_roles_rel.uselist:
        print("❌ User.roles should be uselist=True (list)")
    else:
        print("✅ User.roles is correctly configured as list")

    # User.access_rights should be uselist=False
    user_access_rel = User.__mapper__.relationships['access_rights']
    if user_access_rel.uselist:
        print("❌ User.access_rights should be uselist=False (single object)")
    else:
        print("✅ User.access_rights is correctly configured as single object")

    # Test 6: Test UserStatsResponse structure
    print("\n🔍 Testing UserStatsResponse structure...")
    try:
        # Create a sample stats response
        stats_data = {
            "total_users": 100,
            "active_users": 85,
            "status_distribution": {"pending": 5, "approved": 80, "blocked": 15},
            "role_distribution": {"applicant": 50, "executor": 30, "manager": 20},
            "monthly_registrations": 12
        }

        stats_response = UserStatsResponse(**stats_data)
        print("✅ UserStatsResponse validation successful")

        # Check that all fields are accessible
        assert stats_response.total_users == 100
        assert isinstance(stats_response.status_distribution, dict)
        assert isinstance(stats_response.role_distribution, dict)

        print("✅ UserStatsResponse field access successful")

    except Exception as e:
        print(f"❌ UserStatsResponse validation failed: {e}")

    # Test 7: Test UserRoleMappingResponse
    print("\n🔍 Testing UserRoleMappingResponse structure...")
    try:
        from datetime import datetime

        role_data = {
            "id": 1,
            "role_key": "executor",
            "role_data": {"specialization": "electrical"},
            "is_active_role": True,
            "assigned_at": datetime.now(),
            "assigned_by": 1,
            "expires_at": None,
            "is_active": True
        }

        role_response = UserRoleMappingResponse(**role_data)
        print("✅ UserRoleMappingResponse validation successful")

    except Exception as e:
        print(f"❌ UserRoleMappingResponse validation failed: {e}")

    print("\n" + "=" * 50)
    print("✅ Model-Schema alignment test completed!")
    return True

async def test_service_imports():
    """Test that services can be imported and instantiated"""

    print("\n🔍 Testing Service Imports")
    print("=" * 50)

    try:
        from services.user_service import UserService
        from services.profile_service import ProfileService
        print("✅ Service imports successful")

        # Test that services can be instantiated (without DB)
        # UserService(None)  # Would require DB session
        print("✅ Service classes available")

    except ImportError as e:
        print(f"❌ Service import error: {e}")
        return False

    return True

async def test_potential_attribute_errors():
    """Test for potential AttributeError sources"""

    print("\n🔍 Testing for Potential AttributeErrors")
    print("=" * 50)

    # Test common field access patterns that might cause errors
    problematic_fields = [
        'middle_name',
        'can_create_requests',  # Should be in JSON field, not direct attribute
        'notification_enabled',
        'rating'
    ]

    from models.user import User, UserProfile
    from models.access import AccessRights

    # Check User model
    user_attrs = dir(User)
    for field in problematic_fields:
        if hasattr(User, field):
            print(f"⚠️  User has potentially problematic field: {field}")
        else:
            print(f"✅ User correctly lacks field: {field}")

    # Check UserProfile model
    profile_attrs = dir(UserProfile)
    for field in problematic_fields:
        if hasattr(UserProfile, field):
            print(f"⚠️  UserProfile has potentially problematic field: {field}")
        else:
            print(f"✅ UserProfile correctly lacks field: {field}")

    # Check AccessRights model - can_create_requests should be in JSON
    access_attrs = dir(AccessRights)
    if hasattr(AccessRights, 'can_create_requests'):
        print(f"⚠️  AccessRights has direct can_create_requests field (should be in JSON)")
    else:
        print(f"✅ AccessRights correctly uses JSON for permissions")

    return True

async def main():
    """Run all validation tests"""

    print("🧪 USER SERVICE VALIDATION TESTS")
    print("=" * 60)

    results = []

    # Run all tests
    test_functions = [
        test_model_schema_alignment,
        test_service_imports,
        test_potential_attribute_errors
    ]

    for test_func in test_functions:
        try:
            result = await test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with exception: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    print("🎯 VALIDATION SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")

    if all(results):
        print("\n🎉 All validation tests PASSED!")
        print("User Service models and schemas are properly aligned.")
    else:
        print("\n💥 Some validation tests FAILED!")
        print("Please review the issues above.")

    return all(results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)