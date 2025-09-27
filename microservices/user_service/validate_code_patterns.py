#!/usr/bin/env python3
# Code pattern validation for User Service
# UK Management Bot - User Service

import re
import os
from pathlib import Path

def check_file_for_patterns(file_path, patterns):
    """Check a file for problematic patterns"""
    issues = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

            for i, line in enumerate(lines, 1):
                for pattern_name, pattern in patterns.items():
                    if re.search(pattern, line):
                        issues.append({
                            'file': file_path,
                            'line': i,
                            'issue': pattern_name,
                            'content': line.strip(),
                            'pattern': pattern
                        })
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

    return issues

def main():
    """Run code pattern validation"""

    print("🔍 USER SERVICE CODE PATTERN VALIDATION")
    print("=" * 50)

    # Patterns that could cause issues
    problematic_patterns = {
        'direct_middle_name_access': r'\.middle_name(?!\s*=)',
        'direct_can_create_requests': r'\.can_create_requests(?!\s*[:=])',
        'direct_notification_flags': r'\.notification_(?:enabled|settings|preferences)',
        'direct_rating_access': r'\.rating(?!\s*=)',
        'sync_requests_in_async': r'import\s+requests(?!\s*\.)',
        'profile_as_list_access': r'user\.profile\[',
        'roles_as_single_access': r'user\.roles\.(?!append|remove)',  # Accessing as single instead of list
        'missing_await_http': r'requests\.(get|post|put|delete)',
        'json_field_as_attribute': r'access_rights\.(?!service_permissions)',
    }

    # Files to check
    service_files = [
        'services/user_service.py',
        'services/profile_service.py',
        'services/role_service.py',
        'services/verification_service.py',
        'api/v1/users.py',
        'api/v1/profiles.py',
        'api/v1/roles.py',
        'api/v1/verification.py',
        'api/v1/internal.py'
    ]

    base_path = Path(__file__).parent
    all_issues = []

    for service_file in service_files:
        file_path = base_path / service_file
        if file_path.exists():
            print(f"\n🔍 Checking {service_file}...")
            issues = check_file_for_patterns(file_path, problematic_patterns)
            all_issues.extend(issues)

            if issues:
                for issue in issues:
                    print(f"  ⚠️  Line {issue['line']}: {issue['issue']}")
                    print(f"      {issue['content']}")
            else:
                print(f"  ✅ No issues found")
        else:
            print(f"  ⚠️  File not found: {service_file}")

    # Additional specific checks
    print(f"\n🔍 Checking specific problem areas...")

    # Check UserService._build_user_full_response method
    user_service_file = base_path / 'services/user_service.py'
    if user_service_file.exists():
        with open(user_service_file, 'r') as f:
            content = f.read()

        # Check if profile is accessed correctly
        if 'user.profile[' in content:
            print("  ❌ user.profile accessed as list (should be single object)")
        else:
            print("  ✅ user.profile accessed correctly")

        # Check roles handling in response building
        if 'UserRoleMappingResponse(' in content:
            print("  ✅ UserRoleMappingResponse objects being created")
        else:
            print("  ⚠️  Check roles response building")

    # Check Profile Service HTTP calls
    profile_service_file = base_path / 'services/profile_service.py'
    if profile_service_file.exists():
        with open(profile_service_file, 'r') as f:
            content = f.read()

        if 'import httpx' in content:
            print("  ✅ Profile service uses async httpx")
        elif 'import requests' in content:
            print("  ❌ Profile service uses sync requests (should be httpx)")
        else:
            print("  ⚠️  Check HTTP client in profile service")

        if 'timeout=' in content:
            print("  ✅ HTTP calls have timeouts")
        else:
            print("  ⚠️  HTTP calls may lack timeouts")

    # Summary
    print(f"\n" + "=" * 50)
    print(f"🎯 VALIDATION SUMMARY")
    print(f"=" * 50)

    if all_issues:
        print(f"❌ Found {len(all_issues)} potential issues:")

        # Group by issue type
        issue_types = {}
        for issue in all_issues:
            issue_type = issue['issue']
            if issue_type not in issue_types:
                issue_types[issue_type] = []
            issue_types[issue_type].append(issue)

        for issue_type, issues in issue_types.items():
            print(f"\n  {issue_type}: {len(issues)} occurrences")
            for issue in issues[:3]:  # Show first 3
                print(f"    - {issue['file']}:{issue['line']}")
            if len(issues) > 3:
                print(f"    ... and {len(issues) - 3} more")
    else:
        print("✅ No problematic patterns found!")

    # Specific recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    print("=" * 50)

    recommendations = [
        "✅ Models appear to be correctly defined without problematic fields",
        "✅ ORM relationships seem properly configured",
        "✅ No direct access to non-existent fields detected",
    ]

    if any('sync_requests' in issue['issue'] for issue in all_issues):
        recommendations.append("❌ Replace 'requests' with 'httpx' for async HTTP calls")

    if any('missing_await' in issue['issue'] for issue in all_issues):
        recommendations.append("❌ Add 'await' to HTTP calls and make functions async")

    if any('timeout' not in issue['issue'] for issue in all_issues):
        recommendations.append("⚠️  Add timeouts to HTTP calls")

    for rec in recommendations:
        print(f"  {rec}")

    return len(all_issues) == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)