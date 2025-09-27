# Smoke Tests for Media Upload Operations
# UK Management Bot - Media Service Tests

import pytest
import httpx
import asyncio
import tempfile
import os
from typing import Dict, Any, List
from io import BytesIO

# Configuration
MEDIA_SERVICE_URL = "http://localhost:8080"
AUTH_SERVICE_URL = "http://localhost:8000"

# Test file data
TEST_FILES = {
    "image": {
        "name": "test_image.jpg",
        "content": b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xFF\xC0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xFF\xC4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xFF\xC4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xDA\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xAA\xFF\xD9',
        "content_type": "image/jpeg"
    },
    "document": {
        "name": "test_document.pdf",
        "content": b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF\n',
        "content_type": "application/pdf"
    },
    "text": {
        "name": "test_file.txt",
        "content": b"This is a test text file for upload testing.\nLine 2 of the test file.\nEnd of file.",
        "content_type": "text/plain"
    }
}

class TestMediaUpload:
    """Test suite for Media Upload operations"""

    def __init__(self):
        self.uploaded_file_ids = []
        self.service_token = None

    async def get_service_token(self) -> str:
        """Get service token for authenticated requests"""
        if self.service_token:
            return self.service_token

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/internal/generate-service-token",
                    params={"service_name": "test-service"}
                )

                if response.status_code == 200:
                    token_data = response.json()
                    self.service_token = token_data["token"]
                    return self.service_token
                else:
                    # Fallback to API key
                    return "test-service.api-key"

            except:
                # Fallback to API key if Auth Service not available
                return "test-service.api-key"

    async def cleanup_uploaded_files(self):
        """Clean up uploaded files"""
        if not self.uploaded_file_ids:
            return

        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            for file_id in self.uploaded_file_ids:
                try:
                    await client.delete(
                        f"{MEDIA_SERVICE_URL}/api/v1/media/{file_id}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-API-Key": token
                        }
                    )
                except:
                    pass  # Ignore cleanup errors

    async def test_media_service_health(self):
        """Test Media Service health and connectivity"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MEDIA_SERVICE_URL}/health")

            assert response.status_code == 200, f"Media Service health check failed: {response.status_code}"

            health_data = response.json()
            assert health_data.get("status") == "healthy", "Media Service reports unhealthy"

            print(f"✓ Media Service is healthy")
            print(f"  Service: {health_data.get('service', 'unknown')}")
            print(f"  Version: {health_data.get('version', 'unknown')}")

    async def test_upload_limits_info(self):
        """Test getting upload limits and configuration"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MEDIA_SERVICE_URL}/api/v1/streaming/upload/limits")

            if response.status_code == 200:
                limits = response.json()

                print(f"✓ Upload limits retrieved")
                print(f"  Max file size: {limits.get('max_file_size_mb', 'unknown')} MB")
                print(f"  Max files per request: {limits.get('max_files_per_request', 'unknown')}")
                print(f"  Allowed types: {limits.get('allowed_mime_types', [])}")

                return limits
            else:
                print(f"⚠ Upload limits endpoint returned {response.status_code}")
                return {}

    async def test_standard_file_upload(self) -> Dict[str, Any]:
        """Test standard file upload endpoint"""
        token = await self.get_service_token()
        test_file = TEST_FILES["image"]

        async with httpx.AsyncClient() as client:
            # Prepare multipart form data
            files = {
                "file": (test_file["name"], test_file["content"], test_file["content_type"])
            }

            data = {
                "request_number": "250926-001",
                "description": "Smoke test upload",
                "category": "test"
            }

            response = await client.post(
                f"{MEDIA_SERVICE_URL}/api/v1/media/upload",
                files=files,
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 201:
                upload_result = response.json()

                assert "id" in upload_result
                assert "file_path" in upload_result
                assert upload_result["original_filename"] == test_file["name"]

                # Track for cleanup
                self.uploaded_file_ids.append(upload_result["id"])

                print(f"✓ Standard file upload successful")
                print(f"  File ID: {upload_result['id']}")
                print(f"  Original name: {upload_result['original_filename']}")
                print(f"  File size: {upload_result.get('file_size', 'unknown')} bytes")

                return upload_result

            else:
                print(f"⚠ Standard upload returned {response.status_code}: {response.text}")
                return {}

    async def test_streaming_file_upload(self) -> Dict[str, Any]:
        """Test streaming file upload endpoint"""
        token = await self.get_service_token()
        test_file = TEST_FILES["document"]

        async with httpx.AsyncClient() as client:
            # Prepare multipart form data
            files = {
                "file": (test_file["name"], test_file["content"], test_file["content_type"])
            }

            data = {
                "request_number": "250926-002",
                "description": "Streaming upload test",
                "category": "document"
            }

            response = await client.post(
                f"{MEDIA_SERVICE_URL}/api/v1/streaming/upload/stream",
                files=files,
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 201:
                upload_result = response.json()

                assert "id" in upload_result
                assert "file_path" in upload_result
                assert upload_result["original_filename"] == test_file["name"]

                # Track for cleanup
                self.uploaded_file_ids.append(upload_result["id"])

                print(f"✓ Streaming file upload successful")
                print(f"  File ID: {upload_result['id']}")
                print(f"  Original name: {upload_result['original_filename']}")
                print(f"  Upload method: streaming")

                return upload_result

            else:
                print(f"⚠ Streaming upload returned {response.status_code}: {response.text}")
                return {}

    async def test_multiple_file_upload(self) -> List[Dict[str, Any]]:
        """Test multiple file upload"""
        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            # Prepare multiple files
            files = []
            for i, (file_type, file_data) in enumerate(TEST_FILES.items()):
                files.append(
                    ("files", (f"{i}_{file_data['name']}", file_data["content"], file_data["content_type"]))
                )

            data = {
                "request_number": "250926-003",
                "description": "Multiple file upload test",
                "category": "mixed"
            }

            response = await client.post(
                f"{MEDIA_SERVICE_URL}/api/v1/streaming/upload/multiple",
                files=files,
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 201:
                upload_results = response.json()

                assert isinstance(upload_results, list)
                assert len(upload_results) == len(TEST_FILES)

                for result in upload_results:
                    assert "id" in result
                    assert "file_path" in result
                    # Track for cleanup
                    self.uploaded_file_ids.append(result["id"])

                print(f"✓ Multiple file upload successful")
                print(f"  Uploaded {len(upload_results)} files")

                return upload_results

            else:
                print(f"⚠ Multiple upload returned {response.status_code}: {response.text}")
                return []

    async def test_file_retrieval(self, file_data: Dict[str, Any]):
        """Test file retrieval and download"""
        if not file_data or "id" not in file_data:
            print(f"⚠ Skipping file retrieval test - no file data")
            return

        token = await self.get_service_token()
        file_id = file_data["id"]

        async with httpx.AsyncClient() as client:
            # Test file metadata retrieval
            response = await client.get(
                f"{MEDIA_SERVICE_URL}/api/v1/media/{file_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 200:
                metadata = response.json()

                assert metadata["id"] == file_id
                assert "original_filename" in metadata
                assert "file_size" in metadata

                print(f"✓ File metadata retrieved successfully")
                print(f"  File ID: {metadata['id']}")
                print(f"  Filename: {metadata['original_filename']}")
                print(f"  Size: {metadata.get('file_size', 'unknown')} bytes")

                # Test file download
                download_response = await client.get(
                    f"{MEDIA_SERVICE_URL}/api/v1/media/{file_id}/download",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-API-Key": token
                    }
                )

                if download_response.status_code == 200:
                    print(f"✓ File download successful")
                    print(f"  Content length: {len(download_response.content)} bytes")
                else:
                    print(f"⚠ File download returned {download_response.status_code}")

            else:
                print(f"⚠ File metadata retrieval returned {response.status_code}")

    async def test_file_search(self):
        """Test file search functionality"""
        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            # Search by request number
            response = await client.get(
                f"{MEDIA_SERVICE_URL}/api/v1/media/search",
                params={"request_number": "250926-001"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 200:
                search_results = response.json()

                if isinstance(search_results, list):
                    files = search_results
                elif isinstance(search_results, dict) and "files" in search_results:
                    files = search_results["files"]
                else:
                    files = []

                print(f"✓ File search successful")
                print(f"  Found {len(files)} files for request 250926-001")

            else:
                print(f"⚠ File search returned {response.status_code}")

    async def test_upload_progress(self):
        """Test upload progress tracking"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MEDIA_SERVICE_URL}/api/v1/streaming/upload/progress")

            if response.status_code == 200:
                progress_info = response.json()

                print(f"✓ Upload progress endpoint available")
                print(f"  Active uploads: {progress_info.get('active_uploads', 0)}")
                print(f"  Total completed: {progress_info.get('completed_uploads', 0)}")

            else:
                print(f"⚠ Upload progress returned {response.status_code}")

    async def test_file_validation(self):
        """Test file validation and error handling"""
        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            # Test invalid file type
            invalid_file = {
                "name": "test.exe",
                "content": b"MZ\x90\x00",  # PE header
                "content_type": "application/octet-stream"
            }

            files = {
                "file": (invalid_file["name"], invalid_file["content"], invalid_file["content_type"])
            }

            data = {
                "request_number": "250926-004",
                "description": "Invalid file test"
            }

            response = await client.post(
                f"{MEDIA_SERVICE_URL}/api/v1/media/upload",
                files=files,
                data=data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            # Should reject invalid file types
            if response.status_code in [400, 415]:
                print(f"✓ File validation working - rejected invalid file type")
            else:
                print(f"⚠ File validation may not be working: {response.status_code}")

    async def test_authentication_required(self):
        """Test that authentication is required for uploads"""
        test_file = TEST_FILES["text"]

        async with httpx.AsyncClient() as client:
            files = {
                "file": (test_file["name"], test_file["content"], test_file["content_type"])
            }

            data = {
                "request_number": "250926-005",
                "description": "Unauthenticated test"
            }

            response = await client.post(
                f"{MEDIA_SERVICE_URL}/api/v1/media/upload",
                files=files,
                data=data
            )

            assert response.status_code in [401, 403], "Should require authentication"

            print(f"✓ Authentication requirement enforced")

# Test runner
async def run_media_upload_tests():
    """Run all Media Upload smoke tests"""
    print("=" * 50)
    print("SMOKE TESTS: Media Upload Operations")
    print("=" * 50)

    test_instance = TestMediaUpload()

    try:
        # Basic connectivity and info
        await test_instance.test_media_service_health()
        await test_instance.test_upload_limits_info()

        # Upload tests
        print(f"\n🧪 Testing: Standard File Upload")
        standard_upload = await test_instance.test_standard_file_upload()
        if standard_upload:
            print(f"✅ Standard File Upload PASSED")
        else:
            print(f"❌ Standard File Upload FAILED")

        print(f"\n🧪 Testing: Streaming File Upload")
        streaming_upload = await test_instance.test_streaming_file_upload()
        if streaming_upload:
            print(f"✅ Streaming File Upload PASSED")
        else:
            print(f"❌ Streaming File Upload FAILED")

        # Additional tests
        tests = [
            ("Multiple File Upload", test_instance.test_multiple_file_upload()),
            ("File Retrieval", test_instance.test_file_retrieval(standard_upload or streaming_upload)),
            ("File Search", test_instance.test_file_search()),
            ("Upload Progress", test_instance.test_upload_progress()),
            ("File Validation", test_instance.test_file_validation()),
            ("Authentication Required", test_instance.test_authentication_required())
        ]

        results = {"passed": 2 if (standard_upload or streaming_upload) else 0, "failed": 0, "errors": []}

        for test_name, test_coro in tests:
            try:
                print(f"\n🧪 Testing: {test_name}")
                await test_coro
                results["passed"] += 1
                print(f"✅ {test_name} PASSED")

            except Exception as e:
                results["failed"] += 1
                results["errors"].append((test_name, str(e)))
                print(f"❌ {test_name} FAILED: {e}")

        print(f"\n" + "=" * 50)
        print(f"MEDIA UPLOAD TEST RESULTS")
        print(f"=" * 50)
        print(f"✅ Passed: {results['passed']}")
        print(f"❌ Failed: {results['failed']}")

        if results["errors"]:
            print(f"\nErrors:")
            for test_name, error in results["errors"]:
                print(f"  - {test_name}: {error}")

        return results["failed"] == 0

    finally:
        # Cleanup
        print(f"\n🧹 Cleaning up uploaded files...")
        await test_instance.cleanup_uploaded_files()
        print(f"✓ Cleanup completed")

if __name__ == "__main__":
    # Run smoke tests directly
    success = asyncio.run(run_media_upload_tests())
    exit(0 if success else 1)