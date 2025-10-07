"""
Google Sheets API Endpoints
UK Management Bot - Integration Service
"""

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends

from app.schemas.google_sheets import (
    SheetsReadRequest,
    SheetsReadResponse,
    SheetsWriteRequest,
    SheetsWriteResponse,
    SheetsAppendRequest,
    SheetsAppendResponse,
    SheetsBatchRequest,
    SheetsBatchResponse,
    SpreadsheetMetadata
)
from app.adapters.google_sheets_adapter import GoogleSheetsAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sheets", tags=["Google Sheets"])

# Global adapter instance (initialized on startup)
_sheets_adapter: Optional[GoogleSheetsAdapter] = None


async def get_sheets_adapter(
    x_management_company_id: str = Header(..., description="Tenant ID")
) -> GoogleSheetsAdapter:
    """
    Get Google Sheets adapter instance

    Args:
        x_management_company_id: Tenant ID from header

    Returns:
        GoogleSheetsAdapter instance

    Raises:
        HTTPException: If adapter not initialized
    """
    global _sheets_adapter

    if not _sheets_adapter:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sheets adapter not initialized"
        )

    # For multi-tenant, create adapter per request
    # For now, using global adapter with tenant override
    _sheets_adapter.management_company_id = x_management_company_id

    return _sheets_adapter


async def initialize_sheets_adapter() -> None:
    """Initialize Google Sheets adapter on startup"""
    global _sheets_adapter

    try:
        _sheets_adapter = GoogleSheetsAdapter(
            management_company_id=settings.MANAGEMENT_COMPANY_ID,
            credentials_path=settings.GOOGLE_SHEETS_CREDENTIALS_PATH
        )
        await _sheets_adapter.initialize()
        logger.info("✅ Google Sheets adapter initialized")

    except Exception as e:
        logger.error(f"❌ Failed to initialize Google Sheets adapter: {e}")
        # Don't raise - allow service to start without Sheets


async def shutdown_sheets_adapter() -> None:
    """Shutdown Google Sheets adapter"""
    global _sheets_adapter

    if _sheets_adapter:
        await _sheets_adapter.shutdown()
        _sheets_adapter = None
        logger.info("✅ Google Sheets adapter shutdown complete")


@router.post("/read", response_model=SheetsReadResponse)
async def read_sheet(
    request: SheetsReadRequest,
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> SheetsReadResponse:
    """
    Read data from Google Sheet

    **Parameters**:
    - **spreadsheet_id**: Google Sheet ID (from URL)
    - **range**: A1 notation range (e.g., "Sheet1!A1:D10")
    - **value_render_option**: FORMATTED_VALUE (default), UNFORMATTED_VALUE, or FORMULA

    **Returns**:
    - 2D array of cell values

    **Example**:
    ```json
    {
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "range": "Sheet1!A1:D5",
      "value_render_option": "FORMATTED_VALUE"
    }
    ```
    """
    try:
        values = await adapter.read_range(
            spreadsheet_id=request.spreadsheet_id,
            range_name=request.range,
            value_render_option=request.value_render_option
        )

        return SheetsReadResponse(
            values=values,
            range=request.range,
            cached=False  # TODO: Implement caching
        )

    except Exception as e:
        logger.error(f"Error reading sheet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read sheet: {str(e)}"
        )


@router.post("/write", response_model=SheetsWriteResponse)
async def write_sheet(
    request: SheetsWriteRequest,
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> SheetsWriteResponse:
    """
    Write data to Google Sheet

    **Parameters**:
    - **spreadsheet_id**: Google Sheet ID
    - **range**: A1 notation range (e.g., "Sheet1!A1:D10")
    - **values**: 2D array of values to write
    - **value_input_option**: USER_ENTERED (parse values) or RAW (store as-is)

    **Returns**:
    - Updated range, row count, column count

    **Example**:
    ```json
    {
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "range": "Sheet1!A1:B2",
      "values": [
        ["Name", "Age"],
        ["Alice", 30]
      ],
      "value_input_option": "USER_ENTERED"
    }
    ```
    """
    try:
        result = await adapter.write_range(
            spreadsheet_id=request.spreadsheet_id,
            range_name=request.range,
            values=request.values,
            value_input_option=request.value_input_option
        )

        return SheetsWriteResponse(**result)

    except Exception as e:
        logger.error(f"Error writing to sheet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write to sheet: {str(e)}"
        )


@router.post("/append", response_model=SheetsAppendResponse)
async def append_sheet(
    request: SheetsAppendRequest,
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> SheetsAppendResponse:
    """
    Append rows to the end of a Google Sheet

    **Parameters**:
    - **spreadsheet_id**: Google Sheet ID
    - **range**: A1 notation range (defines columns, e.g., "Sheet1!A:B")
    - **values**: 2D array of values to append
    - **value_input_option**: USER_ENTERED or RAW
    - **insert_data_option**: INSERT_ROWS (default) or OVERWRITE

    **Returns**:
    - Updated range, number of appended rows

    **Example**:
    ```json
    {
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "range": "Sheet1!A:B",
      "values": [
        ["Bob", 25],
        ["Charlie", 35]
      ]
    }
    ```
    """
    try:
        result = await adapter.append_rows(
            spreadsheet_id=request.spreadsheet_id,
            range_name=request.range,
            values=request.values,
            value_input_option=request.value_input_option,
            insert_data_option=request.insert_data_option
        )

        return SheetsAppendResponse(**result)

    except Exception as e:
        logger.error(f"Error appending to sheet: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to append to sheet: {str(e)}"
        )


@router.post("/batch", response_model=SheetsBatchResponse)
async def batch_operations(
    request: SheetsBatchRequest,
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> SheetsBatchResponse:
    """
    Perform batch operations on Google Sheet

    **Parameters**:
    - **spreadsheet_id**: Google Sheet ID
    - **operations**: List of operations (read, write, append)

    **Returns**:
    - Results for each operation

    **Example**:
    ```json
    {
      "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "operations": [
        {
          "operation": "read",
          "range": "Sheet1!A1:B2"
        },
        {
          "operation": "write",
          "range": "Sheet1!C1:D2",
          "values": [[1, 2], [3, 4]]
        },
        {
          "operation": "append",
          "range": "Sheet1!A:B",
          "values": [["Eve", 28]]
        }
      ]
    }
    ```
    """
    try:
        # Convert pydantic models to dicts for adapter
        operations_list = [op.dict(exclude_none=True) for op in request.operations]

        result = await adapter.batch_update(
            spreadsheet_id=request.spreadsheet_id,
            operations=operations_list
        )

        return SheetsBatchResponse(**result)

    except Exception as e:
        logger.error(f"Error in batch operations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform batch operations: {str(e)}"
        )


@router.get("/metadata/{spreadsheet_id}", response_model=SpreadsheetMetadata)
async def get_spreadsheet_metadata(
    spreadsheet_id: str,
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> SpreadsheetMetadata:
    """
    Get spreadsheet metadata

    **Parameters**:
    - **spreadsheet_id**: Google Sheet ID

    **Returns**:
    - Spreadsheet title, URL, sheet list

    **Example**:
    ```
    GET /api/v1/sheets/metadata/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
    ```
    """
    try:
        metadata = await adapter.get_spreadsheet_metadata(
            spreadsheet_id=spreadsheet_id
        )

        return SpreadsheetMetadata(**metadata)

    except Exception as e:
        logger.error(f"Error getting metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Spreadsheet not found: {str(e)}"
        )


@router.get("/health")
async def sheets_health_check(
    adapter: GoogleSheetsAdapter = Depends(get_sheets_adapter)
) -> dict:
    """
    Check Google Sheets API health

    **Returns**:
    - Health status
    """
    try:
        healthy = await adapter.health_check()

        return {
            "service": "google_sheets",
            "status": "healthy" if healthy else "unhealthy",
            "timestamp": "2025-10-07T12:00:00Z"  # TODO: Use actual timestamp
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "service": "google_sheets",
            "status": "error",
            "error": str(e)
        }
