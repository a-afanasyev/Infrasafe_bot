"""
Google Sheets API Schemas
UK Management Bot - Integration Service
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ============ REQUEST SCHEMAS ============

class SheetsReadRequest(BaseModel):
    """Request to read from Google Sheet"""
    spreadsheet_id: str = Field(description="Google Sheet ID")
    range: str = Field(description="A1 notation range (e.g., 'Sheet1!A1:D10')")
    value_render_option: Optional[str] = Field(
        default="FORMATTED_VALUE",
        description="Value render option: FORMATTED_VALUE, UNFORMATTED_VALUE, FORMULA"
    )


class SheetsWriteRequest(BaseModel):
    """Request to write to Google Sheet"""
    spreadsheet_id: str = Field(description="Google Sheet ID")
    range: str = Field(description="A1 notation range")
    values: List[List[Any]] = Field(description="2D array of values to write")
    value_input_option: Optional[str] = Field(
        default="USER_ENTERED",
        description="Value input option: USER_ENTERED or RAW"
    )


class SheetsAppendRequest(BaseModel):
    """Request to append rows to Google Sheet"""
    spreadsheet_id: str = Field(description="Google Sheet ID")
    range: str = Field(description="A1 notation range")
    values: List[List[Any]] = Field(description="2D array of values to append")
    value_input_option: Optional[str] = Field(
        default="USER_ENTERED",
        description="Value input option: USER_ENTERED or RAW"
    )
    insert_data_option: Optional[str] = Field(
        default="INSERT_ROWS",
        description="Insert option: INSERT_ROWS or OVERWRITE"
    )


class SheetsBatchOperation(BaseModel):
    """Single operation in batch request"""
    operation: str = Field(description="Operation type: read, write, append")
    range: str = Field(description="A1 notation range")
    values: Optional[List[List[Any]]] = Field(None, description="Values (for write/append)")
    value_render_option: Optional[str] = Field(None, description="Render option (for read)")
    value_input_option: Optional[str] = Field(None, description="Input option (for write/append)")
    insert_data_option: Optional[str] = Field(None, description="Insert option (for append)")


class SheetsBatchRequest(BaseModel):
    """Request for batch operations"""
    spreadsheet_id: str = Field(description="Google Sheet ID")
    operations: List[SheetsBatchOperation] = Field(description="List of operations")


# ============ RESPONSE SCHEMAS ============

class SheetsReadResponse(BaseModel):
    """Response from read operation"""
    values: List[List[Any]] = Field(description="2D array of values")
    range: str = Field(description="Range that was read")
    cached: bool = Field(default=False, description="Was response cached")
    cache_ttl_seconds: Optional[int] = Field(None, description="Cache TTL if cached")


class SheetsWriteResponse(BaseModel):
    """Response from write operation"""
    updated_range: str = Field(description="Range that was updated")
    updated_rows: int = Field(description="Number of rows updated")
    updated_columns: int = Field(description="Number of columns updated")


class SheetsAppendResponse(BaseModel):
    """Response from append operation"""
    updated_range: str = Field(description="Range that was updated")
    appended_rows: int = Field(description="Number of rows appended")


class SheetsBatchOperationResult(BaseModel):
    """Result of single batch operation"""
    index: int = Field(description="Operation index")
    operation: str = Field(description="Operation type")
    range: str = Field(description="Range")
    success: bool = Field(description="Operation succeeded")
    data: Optional[Any] = Field(None, description="Operation result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    updated_rows: Optional[int] = Field(None, description="Rows updated (for write/append)")
    updated_columns: Optional[int] = Field(None, description="Columns updated (for write)")
    appended_rows: Optional[int] = Field(None, description="Rows appended (for append)")


class SheetsBatchResponse(BaseModel):
    """Response from batch operations"""
    total_operations: int = Field(description="Total operations")
    successful: int = Field(description="Successful operations")
    failed: int = Field(description="Failed operations")
    results: List[SheetsBatchOperationResult] = Field(description="Operation results")


class WorksheetMetadata(BaseModel):
    """Worksheet metadata"""
    id: int = Field(description="Worksheet ID")
    title: str = Field(description="Worksheet title")
    index: int = Field(description="Worksheet index")
    row_count: int = Field(description="Number of rows")
    col_count: int = Field(description="Number of columns")


class SpreadsheetMetadata(BaseModel):
    """Spreadsheet metadata"""
    id: str = Field(description="Spreadsheet ID")
    title: str = Field(description="Spreadsheet title")
    url: str = Field(description="Spreadsheet URL")
    sheet_count: int = Field(description="Number of sheets")
    sheets: List[WorksheetMetadata] = Field(description="Sheet metadata")
