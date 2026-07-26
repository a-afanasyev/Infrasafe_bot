#!/usr/bin/env python3
"""
Тест загрузки файла в MediaService для проверки работы с каналами
"""

import requests
import io
from PIL import Image

def create_test_image():
    """Создаем тестовое изображение в памяти"""
    import random
    # Создаем изображение с случайным цветом для уникальности
    colors = ['red', 'blue', 'green', 'yellow', 'purple', 'orange']
    color = random.choice(colors)
    size = random.randint(90, 110)
    img = Image.new('RGB', (size, size), color=color)

    # Добавляем текст (если доступен)
    try:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), "TEST", fill='white')
    except Exception:
        pass

    # Сохраняем в BytesIO как JPEG
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)

    return img_bytes

def test_upload():
    """Тест загрузки файла"""
    print("🧪 Testing MediaService Upload...")

    api_url = "http://media-api:8000/api/v1/media/upload"

    # Создаем тестовое изображение
    test_image = create_test_image()

    # Подготавливаем данные для загрузки
    files = {
        'file': ('test_image.jpg', test_image, 'image/jpeg')
    }

    data = {
        'request_number': 'TEST-250920-002',
        'category': 'request_photo',
        'description': 'Тестовое изображение для проверки работы каналов',
        'tags': 'test,frontend,channel_test',
        'uploaded_by': '1'
    }

    try:
        print(f"📤 Uploading test image to {api_url}...")
        response = requests.post(api_url, files=files, data=data, timeout=30)

        print(f"📊 Response Status: {response.status_code}")

        if response.status_code == 201:
            result = response.json()
            print("✅ Upload successful!")
            print(f"   File ID: {result['media_file']['id']}")
            print(f"   Filename: {result['media_file']['original_filename']}")
            print(f"   Category: {result['media_file']['category']}")
            print(f"   Request: {result['media_file']['request_number']}")
            print(f"   Tags: {result['media_file']['tags']}")

            if result.get('file_url'):
                print(f"   File URL: {result['file_url']}")

            return True

        else:
            print("❌ Upload failed!")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to MediaService API")
        print("   Make sure the service is running on localhost:8001")
        return False
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return False

def test_search():
    """Тест поиска загруженного файла"""
    print("\n🔍 Testing search for uploaded file...")

    search_url = "http://media-api:8000/api/v1/media/search"
    params = {
        'request_numbers': 'TEST-250920-002',
        'limit': 10
    }

    try:
        response = requests.get(search_url, params=params, timeout=10)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Search successful! Found {result['total_count']} files")

            if result['results']:
                file_info = result['results'][0]
                print(f"   Found file: {file_info['original_filename']}")
                print(f"   Description: {file_info['description']}")
                print(f"   Tags: {file_info['tags']}")

            return True
        else:
            print(f"❌ Search failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Search error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 MediaService Channel Integration Test")
    print("=" * 50)

    # Проверяем загрузку
    upload_success = test_upload()

    # Если загрузка прошла успешно, проверяем поиск
    if upload_success:
        search_success = test_search()

        if search_success:
            print("\n🎉 All tests passed! MediaService channels are working!")
        else:
            print("\n⚠️  Upload works but search has issues")
    else:
        print("\n❌ Upload test failed - check Telegram channel configuration")
        print("\nПроверьте:")
        print("1. Бот добавлен во все каналы как администратор")
        print("2. Бот имеет права на отправку сообщений и медиа")
        print("3. Каналы существуют и доступны")
        print("4. TELEGRAM_BOT_TOKEN корректный")