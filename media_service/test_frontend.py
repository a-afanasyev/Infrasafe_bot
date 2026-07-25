#!/usr/bin/env python3
"""
Тесты для MediaService через фронтенд API
Запускается в контейнере для проверки функциональности
"""

import requests
import time
import sys

class MediaServiceTester:
    def __init__(self):
        # Используем имена контейнеров для доступа к сервисам
        self.api_base = "http://media-api:8000/api/v1"
        self.frontend_base = "http://frontend:80"

    def run_tests(self):
        """Запуск всех тестов"""
        print("🧪 Starting MediaService API Tests")
        print("=" * 50)

        tests = [
            self.test_api_health,
            self.test_frontend_available,
            self.test_statistics,
            self.test_popular_tags,
            self.test_search_empty,
            self.test_timeline_empty,
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                print(f"\n📋 Running: {test.__name__}")
                test()
                print(f"✅ PASSED: {test.__name__}")
                passed += 1
            except Exception as e:
                print(f"❌ FAILED: {test.__name__} - {e}")
                failed += 1

        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed} passed, {failed} failed")

        if failed > 0:
            sys.exit(1)
        else:
            print("🎉 All tests passed!")

    def test_api_health(self):
        """Тест health check API"""
        response = requests.get(f"{self.api_base}/health", timeout=5)
        response.raise_for_status()

        data = response.json()
        assert data["status"] == "ok", f"Expected status 'ok', got {data['status']}"
        assert data["service"] == "media-service", f"Wrong service name: {data['service']}"

        print(f"   ✓ API is healthy: {data['service']} v{data['version']}")

    def test_frontend_available(self):
        """Тест доступности фронтенда"""
        response = requests.get(self.frontend_base, timeout=5)
        response.raise_for_status()

        html = response.text
        assert "UK Media Service - Test Frontend" in html, "Frontend title not found"
        assert "Bootstrap" in html, "Bootstrap not loaded"

        print("   ✓ Frontend is accessible and properly rendered")

    def test_statistics(self):
        """Тест получения статистики"""
        response = requests.get(f"{self.api_base}/media/statistics", timeout=10)
        response.raise_for_status()

        stats = response.json()
        required_fields = ["total_files", "total_size_mb", "file_types", "categories", "top_tags"]

        for field in required_fields:
            assert field in stats, f"Missing field in statistics: {field}"

        assert isinstance(stats["total_files"], int), "total_files should be integer"
        assert isinstance(stats["total_size_mb"], (int, float)), "total_size_mb should be number"
        assert isinstance(stats["file_types"], list), "file_types should be list"

        print(f"   ✓ Statistics retrieved: {stats['total_files']} files, {stats['total_size_mb']} MB")

    def test_popular_tags(self):
        """Тест получения популярных тегов"""
        response = requests.get(f"{self.api_base}/media/tags/popular?limit=10", timeout=5)
        response.raise_for_status()

        tags = response.json()
        assert isinstance(tags, list), "Popular tags should be a list"

        # Проверяем структуру тегов если они есть
        if tags:
            tag = tags[0]
            required_fields = ["tag", "count"]
            for field in required_fields:
                assert field in tag, f"Missing field in tag: {field}"

        print(f"   ✓ Popular tags retrieved: {len(tags)} tags")

    def test_search_empty(self):
        """Тест поиска с пустыми результатами"""
        response = requests.get(f"{self.api_base}/media/search?query=nonexistent_test_query", timeout=5)
        response.raise_for_status()

        data = response.json()
        required_fields = ["results", "total_count", "limit", "offset", "has_more"]

        for field in required_fields:
            assert field in data, f"Missing field in search results: {field}"

        assert isinstance(data["results"], list), "Results should be a list"
        assert data["total_count"] >= 0, "Total count should be non-negative"

        print(f"   ✓ Search works: {data['total_count']} results found")

    def test_timeline_empty(self):
        """Тест временной линии для несуществующей заявки"""
        response = requests.get(f"{self.api_base}/media/request/NONEXISTENT-001/timeline", timeout=5)
        response.raise_for_status()

        data = response.json()
        required_fields = ["request_number", "timeline", "total_files"]

        for field in required_fields:
            assert field in data, f"Missing field in timeline: {field}"

        assert data["request_number"] == "NONEXISTENT-001", "Wrong request number in response"
        assert isinstance(data["timeline"], list), "Timeline should be a list"
        assert data["total_files"] == 0, "Total files should be 0 for nonexistent request"

        print(f"   ✓ Timeline works: {data['total_files']} files for {data['request_number']}")

def main():
    """Основная функция"""
    print("🚀 MediaService Frontend & API Tester")
    print("Running in Docker container environment")

    # Ждем запуска сервисов
    print("\n⏳ Waiting for services to be ready...")
    time.sleep(5)

    tester = MediaServiceTester()
    tester.run_tests()

if __name__ == "__main__":
    main()