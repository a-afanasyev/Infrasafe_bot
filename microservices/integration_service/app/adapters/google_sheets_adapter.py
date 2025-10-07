"""
Google Sheets Adapter
UK Management Bot - Integration Service

Provides async access to Google Sheets API with:
- Read/write/append operations
- Batch operations
- Rate limiting
- Automatic retries
- Error handling
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

import gspread_asyncio
from google.oauth2.service_account import Credentials
from gspread_asyncio import AsyncioGspreadClientManager

from app.adapters.base import BaseAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleSheetsAdapter(BaseAdapter):
    """
    Google Sheets API Adapter

    Features:
    - Async API operations
    - Service account authentication
    - Rate limiting (100 req/min)
    - Automatic retries on failures
    - Full read/write/append support
    """

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.readonly'
    ]

    def __init__(
        self,
        management_company_id: str,
        credentials_path: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Google Sheets adapter

        Args:
            management_company_id: Tenant ID
            credentials_path: Path to service account JSON
            config: Optional configuration
        """
        super().__init__(
            service_name="google_sheets",
            service_type="sheets",
            management_company_id=management_company_id,
            config=config or {}
        )

        self.credentials_path = credentials_path or settings.GOOGLE_SHEETS_CREDENTIALS_PATH
        self.rate_limit_per_minute = settings.GOOGLE_SHEETS_RATE_LIMIT_PER_MINUTE

        self._client_manager: Optional[AsyncioGspreadClientManager] = None
        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._request_window_start: float = 0.0

    async def initialize(self) -> None:
        """Initialize Google Sheets API client"""
        try:
            if not self.credentials_path:
                raise ValueError("Google Sheets credentials path not configured")

            # Create credentials provider
            def get_creds():
                return Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=self.SCOPES
                )

            # Create async client manager
            self._client_manager = AsyncioGspreadClientManager(get_creds)

            # Test authentication
            await self.health_check()

            self.logger.info(f"✅ Google Sheets adapter initialized for tenant {self.management_company_id}")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Google Sheets adapter: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown Google Sheets client"""
        try:
            # gspread-asyncio doesn't require explicit cleanup
            self._client_manager = None
            self.logger.info("✅ Google Sheets adapter shutdown complete")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

    async def health_check(self) -> bool:
        """
        Check Google Sheets API health

        Returns:
            True if API is accessible
        """
        try:
            if not self._client_manager:
                return False

            # Try to get authorized client
            client = await self._client_manager.authorize()

            # Simple API call to verify connectivity
            # This doesn't count against quotas
            await client.list_spreadsheet_files()

            return True

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    async def _rate_limit(self) -> None:
        """
        Enforce rate limiting (100 req/min)

        Uses token bucket algorithm with async sleep.
        """
        current_time = asyncio.get_event_loop().time()

        # Reset window if needed (every 60 seconds)
        if current_time - self._request_window_start >= 60.0:
            self._request_window_start = current_time
            self._request_count = 0

        # Check if we've exceeded rate limit
        if self._request_count >= self.rate_limit_per_minute:
            # Calculate sleep time until window resets
            sleep_time = 60.0 - (current_time - self._request_window_start)
            if sleep_time > 0:
                self.logger.warning(
                    f"⚠️ Rate limit reached ({self.rate_limit_per_minute} req/min), "
                    f"sleeping for {sleep_time:.2f}s"
                )
                await asyncio.sleep(sleep_time)

                # Reset window
                self._request_window_start = asyncio.get_event_loop().time()
                self._request_count = 0

        # Increment request count
        self._request_count += 1

    async def _get_client(self):
        """Get authorized gspread client"""
        if not self._client_manager:
            raise RuntimeError("Adapter not initialized")

        await self._rate_limit()
        return await self._client_manager.authorize()

    async def read_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        value_render_option: str = "FORMATTED_VALUE",
        request_id: Optional[str] = None
    ) -> List[List[Any]]:
        """
        Read data from Google Sheet range

        Args:
            spreadsheet_id: Google Sheet ID
            range_name: A1 notation range (e.g., "Sheet1!A1:D10")
            value_render_option: FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA
            request_id: Optional request ID for tracing

        Returns:
            List of rows, where each row is a list of cell values

        Raises:
            gspread.exceptions.SpreadsheetNotFound: Sheet not found
            gspread.exceptions.WorksheetNotFound: Worksheet not found
        """
        return await self._execute_with_logging(
            operation="sheets_read",
            func=lambda: self._read_range_impl(
                spreadsheet_id,
                range_name,
                value_render_option
            ),
            params={
                "spreadsheet_id": spreadsheet_id,
                "range_name": range_name,
                "value_render_option": value_render_option
            },
            request_id=request_id
        )

    async def _read_range_impl(
        self,
        spreadsheet_id: str,
        range_name: str,
        value_render_option: str
    ) -> List[List[Any]]:
        """Implementation of read_range"""
        client = await self._get_client()
        spreadsheet = await client.open_by_key(spreadsheet_id)

        # Parse range (e.g., "Sheet1!A1:D10" -> sheet_name="Sheet1", range="A1:D10")
        if "!" in range_name:
            sheet_name, cell_range = range_name.split("!", 1)
            worksheet = await spreadsheet.worksheet(sheet_name)
        else:
            # Use first sheet if no sheet specified
            worksheet = await spreadsheet.get_worksheet(0)
            cell_range = range_name

        # Get values
        values = await worksheet.get(cell_range, value_render_option=value_render_option)

        return values

    async def write_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Write data to Google Sheet range

        Args:
            spreadsheet_id: Google Sheet ID
            range_name: A1 notation range (e.g., "Sheet1!A1:D10")
            values: 2D list of values to write
            value_input_option: USER_ENTERED (parse values) or RAW (store as-is)
            request_id: Optional request ID for tracing

        Returns:
            Response dict with updated_range, updated_rows, updated_columns

        Raises:
            gspread.exceptions.SpreadsheetNotFound: Sheet not found
        """
        return await self._execute_with_logging(
            operation="sheets_write",
            func=lambda: self._write_range_impl(
                spreadsheet_id,
                range_name,
                values,
                value_input_option
            ),
            params={
                "spreadsheet_id": spreadsheet_id,
                "range_name": range_name,
                "rows": len(values),
                "columns": len(values[0]) if values else 0,
                "value_input_option": value_input_option
            },
            request_id=request_id
        )

    async def _write_range_impl(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str
    ) -> Dict[str, Any]:
        """Implementation of write_range"""
        client = await self._get_client()
        spreadsheet = await client.open_by_key(spreadsheet_id)

        # Parse range
        if "!" in range_name:
            sheet_name, cell_range = range_name.split("!", 1)
            worksheet = await spreadsheet.worksheet(sheet_name)
        else:
            worksheet = await spreadsheet.get_worksheet(0)
            cell_range = range_name

        # Update values
        await worksheet.update(cell_range, values, value_input_option=value_input_option)

        return {
            "updated_range": range_name,
            "updated_rows": len(values),
            "updated_columns": len(values[0]) if values else 0
        }

    async def append_rows(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
        insert_data_option: str = "INSERT_ROWS",
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Append rows to the end of a Google Sheet

        Args:
            spreadsheet_id: Google Sheet ID
            range_name: A1 notation range (e.g., "Sheet1!A1:D1")
            values: 2D list of values to append
            value_input_option: USER_ENTERED or RAW
            insert_data_option: INSERT_ROWS or OVERWRITE
            request_id: Optional request ID for tracing

        Returns:
            Response dict with updated_range, appended_rows

        Raises:
            gspread.exceptions.SpreadsheetNotFound: Sheet not found
        """
        return await self._execute_with_logging(
            operation="sheets_append",
            func=lambda: self._append_rows_impl(
                spreadsheet_id,
                range_name,
                values,
                value_input_option,
                insert_data_option
            ),
            params={
                "spreadsheet_id": spreadsheet_id,
                "range_name": range_name,
                "rows": len(values),
                "value_input_option": value_input_option
            },
            request_id=request_id
        )

    async def _append_rows_impl(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str,
        insert_data_option: str
    ) -> Dict[str, Any]:
        """Implementation of append_rows"""
        client = await self._get_client()
        spreadsheet = await client.open_by_key(spreadsheet_id)

        # Parse range
        if "!" in range_name:
            sheet_name, cell_range = range_name.split("!", 1)
            worksheet = await spreadsheet.worksheet(sheet_name)
        else:
            worksheet = await spreadsheet.get_worksheet(0)

        # Append rows
        await worksheet.append_rows(
            values,
            value_input_option=value_input_option,
            insert_data_option=insert_data_option
        )

        return {
            "updated_range": range_name,
            "appended_rows": len(values)
        }

    async def batch_update(
        self,
        spreadsheet_id: str,
        operations: List[Dict[str, Any]],
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform batch operations on Google Sheet

        Args:
            spreadsheet_id: Google Sheet ID
            operations: List of operations, each with:
                - operation: "read", "write", or "append"
                - range: A1 notation range
                - values: (for write/append only) 2D list of values
            request_id: Optional request ID for tracing

        Returns:
            Dict with results for each operation

        Example:
            operations = [
                {"operation": "read", "range": "Sheet1!A1:B2"},
                {"operation": "write", "range": "Sheet1!C1:D2", "values": [[1, 2], [3, 4]]},
                {"operation": "append", "range": "Sheet1!A:B", "values": [[5, 6]]}
            ]
        """
        return await self._execute_with_logging(
            operation="sheets_batch",
            func=lambda: self._batch_update_impl(spreadsheet_id, operations),
            params={
                "spreadsheet_id": spreadsheet_id,
                "operations_count": len(operations)
            },
            request_id=request_id
        )

    async def _batch_update_impl(
        self,
        spreadsheet_id: str,
        operations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Implementation of batch_update"""
        results = []

        for i, op in enumerate(operations):
            operation_type = op.get("operation")
            range_name = op.get("range")

            try:
                if operation_type == "read":
                    result = await self._read_range_impl(
                        spreadsheet_id,
                        range_name,
                        op.get("value_render_option", "FORMATTED_VALUE")
                    )
                    results.append({
                        "index": i,
                        "operation": operation_type,
                        "range": range_name,
                        "success": True,
                        "data": result
                    })

                elif operation_type == "write":
                    values = op.get("values", [])
                    result = await self._write_range_impl(
                        spreadsheet_id,
                        range_name,
                        values,
                        op.get("value_input_option", "USER_ENTERED")
                    )
                    results.append({
                        "index": i,
                        "operation": operation_type,
                        "range": range_name,
                        "success": True,
                        **result
                    })

                elif operation_type == "append":
                    values = op.get("values", [])
                    result = await self._append_rows_impl(
                        spreadsheet_id,
                        range_name,
                        values,
                        op.get("value_input_option", "USER_ENTERED"),
                        op.get("insert_data_option", "INSERT_ROWS")
                    )
                    results.append({
                        "index": i,
                        "operation": operation_type,
                        "range": range_name,
                        "success": True,
                        **result
                    })

                else:
                    results.append({
                        "index": i,
                        "operation": operation_type,
                        "success": False,
                        "error": f"Unknown operation: {operation_type}"
                    })

            except Exception as e:
                results.append({
                    "index": i,
                    "operation": operation_type,
                    "range": range_name,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total_operations": len(operations),
            "successful": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "results": results
        }

    async def get_spreadsheet_metadata(
        self,
        spreadsheet_id: str,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get spreadsheet metadata (title, sheets, etc.)

        Args:
            spreadsheet_id: Google Sheet ID
            request_id: Optional request ID for tracing

        Returns:
            Dict with spreadsheet metadata
        """
        return await self._execute_with_logging(
            operation="sheets_metadata",
            func=lambda: self._get_spreadsheet_metadata_impl(spreadsheet_id),
            params={"spreadsheet_id": spreadsheet_id},
            request_id=request_id
        )

    async def _get_spreadsheet_metadata_impl(
        self,
        spreadsheet_id: str
    ) -> Dict[str, Any]:
        """Implementation of get_spreadsheet_metadata"""
        client = await self._get_client()
        spreadsheet = await client.open_by_key(spreadsheet_id)

        worksheets = await spreadsheet.worksheets()

        return {
            "id": spreadsheet.id,
            "title": spreadsheet.title,
            "url": spreadsheet.url,
            "sheet_count": len(worksheets),
            "sheets": [
                {
                    "id": ws.id,
                    "title": ws.title,
                    "index": ws.index,
                    "row_count": ws.row_count,
                    "col_count": ws.col_count
                }
                for ws in worksheets
            ]
        }
