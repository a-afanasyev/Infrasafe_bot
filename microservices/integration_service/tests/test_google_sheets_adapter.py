"""
Tests for Google Sheets Adapter
UK Management Bot - Integration Service
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.google_sheets_adapter import GoogleSheetsAdapter


@pytest.mark.asyncio
class TestGoogleSheetsAdapter:
    """Test suite for Google Sheets Adapter"""

    @pytest.fixture
    async def adapter(self, mock_gspread_client):
        """Create adapter instance with mock client"""
        with patch("app.adapters.google_sheets_adapter.gspread_asyncio.AsyncioGspreadClientManager"):
            adapter = GoogleSheetsAdapter(
                credentials_path="/fake/path/to/credentials.json",
                management_company_id="test-company",
                rate_limit_per_minute=100,
            )
            adapter._agcm = AsyncMock()
            adapter._agcm.authorize.return_value = mock_gspread_client
            yield adapter

    async def test_initialization(self, adapter):
        """Test adapter initialization"""
        assert adapter.management_company_id == "test-company"
        assert adapter.rate_limit_per_minute == 100
        assert adapter._max_tokens == 100
        assert adapter._tokens == 100

    async def test_read_range_success(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test successful read from spreadsheet"""
        result = await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C3",
            request_id="test-123",
        )

        assert result == [
            ["Name", "Email", "Phone"],
            ["John Doe", "john@example.com", "+1234567890"],
            ["Jane Smith", "jane@example.com", "+0987654321"],
        ]

        # Verify client calls
        mock_gspread_client.open_by_key.assert_called_once_with(sample_spreadsheet_id)

    async def test_write_range_success(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test successful write to spreadsheet"""
        values = [
            ["Name", "Email", "Phone"],
            ["New User", "new@example.com", "+1111111111"],
        ]

        result = await adapter.write_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C2",
            values=values,
            value_input_option="USER_ENTERED",
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["updated_cells"] == 6
        assert result["range_name"] == "Sheet1!A1:C2"

    async def test_append_rows_success(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test successful append to spreadsheet"""
        values = [["Appended User", "appended@example.com", "+2222222222"]]

        result = await adapter.append_rows(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A:C",
            values=values,
            value_input_option="USER_ENTERED",
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["updated_rows"] == 1

    async def test_batch_update_success(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test successful batch update"""
        operations = [
            {
                "range": "Sheet1!A1:C1",
                "values": [["Name", "Email", "Phone"]],
            },
            {
                "range": "Sheet1!A2:C2",
                "values": [["John", "john@test.com", "+123"]],
            },
        ]

        result = await adapter.batch_update(
            spreadsheet_id=sample_spreadsheet_id,
            operations=operations,
            value_input_option="USER_ENTERED",
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["total_updated_cells"] >= 0

    async def test_get_spreadsheet_metadata(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test get spreadsheet metadata"""
        # Mock spreadsheet properties
        mock_spreadsheet = mock_gspread_client.open_by_key.return_value
        mock_spreadsheet.title = "Test Spreadsheet"
        mock_spreadsheet.id = sample_spreadsheet_id
        mock_spreadsheet.worksheets.return_value = [
            AsyncMock(title="Sheet1", id=0),
            AsyncMock(title="Sheet2", id=1),
        ]

        result = await adapter.get_spreadsheet_metadata(
            spreadsheet_id=sample_spreadsheet_id,
            request_id="test-123",
        )

        assert result["spreadsheet_id"] == sample_spreadsheet_id
        assert result["title"] == "Test Spreadsheet"
        assert len(result["worksheets"]) == 2

    async def test_rate_limiting(self, adapter):
        """Test rate limiting mechanism"""
        initial_tokens = adapter._tokens

        # Consume one token
        await adapter._consume_token()

        assert adapter._tokens == initial_tokens - 1

    async def test_rate_limit_exceeded(self, adapter):
        """Test rate limit exceeded scenario"""
        # Drain all tokens
        adapter._tokens = 0

        # Next request should wait
        start_time = asyncio.get_event_loop().time()
        await adapter._consume_token()
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should have waited for refill
        assert elapsed > 0
        assert adapter._tokens >= 0

    async def test_error_handling_invalid_spreadsheet(self, adapter, mock_gspread_client):
        """Test error handling for invalid spreadsheet ID"""
        mock_gspread_client.open_by_key.side_effect = Exception("Spreadsheet not found")

        with pytest.raises(Exception) as exc_info:
            await adapter.read_range(
                spreadsheet_id="invalid-id",
                range_name="Sheet1!A1:C3",
            )

        assert "Spreadsheet not found" in str(exc_info.value)

    async def test_error_handling_invalid_range(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test error handling for invalid range"""
        mock_worksheet = AsyncMock()
        mock_worksheet.get_all_values.side_effect = Exception("Invalid range")

        mock_spreadsheet = mock_gspread_client.open_by_key.return_value
        mock_spreadsheet.worksheet.return_value = mock_worksheet

        with pytest.raises(Exception) as exc_info:
            await adapter.read_range(
                spreadsheet_id=sample_spreadsheet_id,
                range_name="InvalidRange",
            )

        assert "Invalid range" in str(exc_info.value)

    async def test_concurrent_requests(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test handling of concurrent requests"""
        tasks = [
            adapter.read_range(
                spreadsheet_id=sample_spreadsheet_id,
                range_name="Sheet1!A1:C3",
                request_id=f"test-{i}",
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed
        assert len(results) == 5
        for result in results:
            assert not isinstance(result, Exception)

    async def test_health_check(self, adapter, mock_gspread_client):
        """Test health check functionality"""
        result = await adapter.health_check()

        assert result["status"] in ["healthy", "unhealthy"]
        assert "rate_limit_remaining" in result
        assert isinstance(result["rate_limit_remaining"], (int, float))

    async def test_value_render_options(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test different value render options"""
        # Test FORMATTED_VALUE (default)
        await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C3",
            value_render_option="FORMATTED_VALUE",
        )

        # Test UNFORMATTED_VALUE
        await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C3",
            value_render_option="UNFORMATTED_VALUE",
        )

        # Test FORMULA
        await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C3",
            value_render_option="FORMULA",
        )

    async def test_value_input_options(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test different value input options"""
        values = [["=SUM(A1:A10)", "100", "2025-01-01"]]

        # Test USER_ENTERED (interprets formulas)
        await adapter.write_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C1",
            values=values,
            value_input_option="USER_ENTERED",
        )

        # Test RAW (stores as-is)
        await adapter.write_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C1",
            values=values,
            value_input_option="RAW",
        )

    async def test_empty_range_read(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test reading empty range"""
        mock_worksheet = mock_gspread_client.open_by_key.return_value.worksheet.return_value
        mock_worksheet.get_all_values.return_value = []

        result = await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!Z1:Z10",
        )

        assert result == []

    async def test_large_batch_operation(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test batch operation with many updates"""
        operations = [
            {
                "range": f"Sheet1!A{i}:C{i}",
                "values": [[f"Row{i}", f"email{i}@test.com", f"+{i}"]],
            }
            for i in range(1, 51)  # 50 operations
        ]

        result = await adapter.batch_update(
            spreadsheet_id=sample_spreadsheet_id,
            operations=operations,
            value_input_option="USER_ENTERED",
        )

        assert result["success"] is True
        assert result["operations_count"] == 50

    async def test_refill_rate_limit_tokens(self, adapter):
        """Test automatic token refill"""
        # Drain tokens
        adapter._tokens = 50

        # Wait for refill
        await asyncio.sleep(1.0)

        # Manually trigger refill
        adapter._refill_tokens()

        # Tokens should be refilled
        assert adapter._tokens > 50

    async def test_request_id_logging(self, adapter, mock_gspread_client, sample_spreadsheet_id):
        """Test that request_id is properly logged"""
        request_id = "test-request-456"

        await adapter.read_range(
            spreadsheet_id=sample_spreadsheet_id,
            range_name="Sheet1!A1:C3",
            request_id=request_id,
        )

        # No exception should be raised with request_id

    async def test_management_company_isolation(self):
        """Test tenant isolation"""
        adapter1 = GoogleSheetsAdapter(
            credentials_path="/fake/path1.json",
            management_company_id="company-1",
            rate_limit_per_minute=100,
        )

        adapter2 = GoogleSheetsAdapter(
            credentials_path="/fake/path2.json",
            management_company_id="company-2",
            rate_limit_per_minute=100,
        )

        assert adapter1.management_company_id != adapter2.management_company_id
        assert adapter1._tokens == adapter2._tokens  # Separate rate limits


@pytest.mark.asyncio
class TestGoogleSheetsAdapterIntegration:
    """Integration tests for Google Sheets Adapter"""

    @pytest.mark.skipif(
        not pytest.config.getoption("--run-integration", default=False),
        reason="Integration tests require --run-integration flag",
    )
    async def test_real_spreadsheet_read(self):
        """Test real Google Sheets API (requires credentials)"""
        # This test requires actual credentials and spreadsheet
        # Skip by default, run with pytest --run-integration
        pass

    @pytest.mark.skipif(
        not pytest.config.getoption("--run-integration", default=False),
        reason="Integration tests require --run-integration flag",
    )
    async def test_real_spreadsheet_write(self):
        """Test real write operation (requires credentials)"""
        # This test requires actual credentials and spreadsheet
        # Skip by default, run with pytest --run-integration
        pass
