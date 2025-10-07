"""
Input Validation
UK Management Bot - Bot Gateway Service

Comprehensive input validation to prevent injection attacks and data corruption.
"""

import re
import logging
from typing import Optional, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails"""
    pass


class InputValidator:
    """
    Input validation utilities for Bot Gateway.

    Protects against:
    - SQL injection
    - XSS attacks
    - Command injection
    - Path traversal
    - Buffer overflow
    - Invalid data types
    """

    # Regular expressions for validation
    PATTERNS = {
        # Telegram user ID (positive integer, max 10 digits)
        "telegram_id": re.compile(r"^[1-9]\d{0,9}$"),

        # Request number (YYMMDD-NNN format)
        "request_number": re.compile(r"^\d{6}-\d{3}$"),

        # UUID v4
        "uuid": re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE
        ),

        # Phone number (international format)
        "phone": re.compile(r"^\+?[1-9]\d{1,14}$"),

        # Email
        "email": re.compile(
            r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        ),

        # Date (YYYY-MM-DD)
        "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),

        # Time (HH:MM or HH:MM:SS)
        "time": re.compile(r"^\d{2}:\d{2}(:\d{2})?$"),

        # Alphanumeric with spaces and basic punctuation
        "safe_text": re.compile(r"^[a-zA-Zа-яА-ЯёЁўЎқҚғҒҳҲ0-9\s.,!?-]+$"),

        # Building address (allow more characters)
        "address": re.compile(r"^[a-zA-Zа-яА-ЯёЁўЎқҚғҒҳҲ0-9\s.,/-]+$"),

        # Specialization code
        "specialization": re.compile(r"^[a-z_]+$"),

        # ISO 8601 datetime
        "iso_datetime": re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?([+-]\d{2}:\d{2}|Z)?$"
        ),

        # File path (safe, no traversal)
        "safe_path": re.compile(r"^[a-zA-Z0-9_/-]+\.[a-zA-Z0-9]+$"),
    }

    # Dangerous patterns to reject
    DANGEROUS_PATTERNS = [
        re.compile(r"<script", re.IGNORECASE),  # XSS
        re.compile(r"javascript:", re.IGNORECASE),  # XSS
        re.compile(r"on\w+\s*=", re.IGNORECASE),  # Event handlers
        re.compile(r"\.\.\/"),  # Path traversal
        re.compile(r"\$\("),  # Command substitution
        re.compile(r"`"),  # Backticks
        re.compile(r";.*--"),  # SQL comments
        re.compile(r"union\s+select", re.IGNORECASE),  # SQL injection
        re.compile(r"drop\s+table", re.IGNORECASE),  # SQL injection
        re.compile(r"exec\s*\(", re.IGNORECASE),  # Code execution
        re.compile(r"eval\s*\(", re.IGNORECASE),  # Code execution
    ]

    # Max lengths for different fields
    MAX_LENGTHS = {
        "text_short": 255,
        "text_medium": 1000,
        "text_long": 4096,  # Telegram message limit
        "description": 2000,
        "comment": 500,
        "address": 200,
        "name": 100,
        "phone": 20,
        "email": 100,
    }

    @classmethod
    def validate_telegram_id(cls, value: Any) -> int:
        """
        Validate Telegram user ID.

        Args:
            value: Value to validate

        Returns:
            Validated integer

        Raises:
            ValidationError: If validation fails
        """
        try:
            telegram_id = int(value)
            if telegram_id <= 0 or telegram_id > 9999999999:
                raise ValidationError("Invalid Telegram ID range")
            return telegram_id
        except (TypeError, ValueError):
            raise ValidationError("Telegram ID must be a positive integer")

    @classmethod
    def validate_request_number(cls, value: str) -> str:
        """Validate request number format (YYMMDD-NNN)"""
        if not isinstance(value, str):
            raise ValidationError("Request number must be a string")

        if not cls.PATTERNS["request_number"].match(value):
            raise ValidationError("Invalid request number format (expected YYMMDD-NNN)")

        return value

    @classmethod
    def validate_uuid(cls, value: str) -> str:
        """Validate UUID v4 format"""
        if not isinstance(value, str):
            raise ValidationError("UUID must be a string")

        if not cls.PATTERNS["uuid"].match(value):
            raise ValidationError("Invalid UUID format")

        return value

    @classmethod
    def validate_phone(cls, value: str) -> str:
        """Validate phone number"""
        if not isinstance(value, str):
            raise ValidationError("Phone must be a string")

        # Remove spaces and dashes
        cleaned = value.replace(" ", "").replace("-", "")

        if not cls.PATTERNS["phone"].match(cleaned):
            raise ValidationError("Invalid phone number format")

        return cleaned

    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate email address"""
        if not isinstance(value, str):
            raise ValidationError("Email must be a string")

        if len(value) > cls.MAX_LENGTHS["email"]:
            raise ValidationError(f"Email too long (max {cls.MAX_LENGTHS['email']})")

        if not cls.PATTERNS["email"].match(value):
            raise ValidationError("Invalid email format")

        return value.lower()

    @classmethod
    def validate_date(cls, value: str) -> date:
        """Validate and parse date string (YYYY-MM-DD)"""
        if not isinstance(value, str):
            raise ValidationError("Date must be a string")

        if not cls.PATTERNS["date"].match(value):
            raise ValidationError("Invalid date format (expected YYYY-MM-DD)")

        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValidationError(f"Invalid date: {e}")

    @classmethod
    def validate_time(cls, value: str) -> str:
        """Validate time string (HH:MM or HH:MM:SS)"""
        if not isinstance(value, str):
            raise ValidationError("Time must be a string")

        if not cls.PATTERNS["time"].match(value):
            raise ValidationError("Invalid time format (expected HH:MM or HH:MM:SS)")

        # Validate hour and minute ranges
        parts = value.split(":")
        hour, minute = int(parts[0]), int(parts[1])

        if hour < 0 or hour > 23:
            raise ValidationError("Hour must be 0-23")
        if minute < 0 or minute > 59:
            raise ValidationError("Minute must be 0-59")

        if len(parts) == 3:
            second = int(parts[2])
            if second < 0 or second > 59:
                raise ValidationError("Second must be 0-59")

        return value

    @classmethod
    def validate_text(
        cls,
        value: str,
        max_length: Optional[int] = None,
        allow_empty: bool = False,
        field_name: str = "text"
    ) -> str:
        """
        Validate text input.

        Args:
            value: Text to validate
            max_length: Maximum allowed length
            allow_empty: Whether empty strings are allowed
            field_name: Field name for error messages

        Returns:
            Validated text

        Raises:
            ValidationError: If validation fails
        """
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string")

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(value):
                raise ValidationError(f"{field_name} contains dangerous content")

        # Strip whitespace
        value = value.strip()

        # Check empty
        if not allow_empty and not value:
            raise ValidationError(f"{field_name} cannot be empty")

        # Check length
        max_len = max_length or cls.MAX_LENGTHS["text_long"]
        if len(value) > max_len:
            raise ValidationError(f"{field_name} too long (max {max_len} characters)")

        return value

    @classmethod
    def validate_address(cls, value: str) -> str:
        """Validate building address"""
        value = cls.validate_text(
            value,
            max_length=cls.MAX_LENGTHS["address"],
            allow_empty=False,
            field_name="address"
        )

        if not cls.PATTERNS["address"].match(value):
            raise ValidationError("Address contains invalid characters")

        return value

    @classmethod
    def validate_specialization(cls, value: str) -> str:
        """Validate specialization code"""
        if not isinstance(value, str):
            raise ValidationError("Specialization must be a string")

        value = value.lower().strip()

        if not cls.PATTERNS["specialization"].match(value):
            raise ValidationError("Invalid specialization format")

        # Check against known specializations
        valid_specs = {
            "plumber", "electrician", "carpenter", "hvac",
            "cleaner", "landscaper", "security", "handyman",
            "painter", "locksmith"
        }

        if value not in valid_specs:
            raise ValidationError(f"Unknown specialization: {value}")

        return value

    @classmethod
    def validate_priority(cls, value: str) -> str:
        """Validate request priority"""
        if not isinstance(value, str):
            raise ValidationError("Priority must be a string")

        valid_priorities = {"low", "medium", "high", "urgent"}

        value = value.lower().strip()

        if value not in valid_priorities:
            raise ValidationError(f"Invalid priority (must be one of: {valid_priorities})")

        return value

    @classmethod
    def validate_status(cls, value: str, valid_statuses: set[str]) -> str:
        """
        Validate status value against allowed statuses.

        Args:
            value: Status value
            valid_statuses: Set of valid status values

        Returns:
            Validated status

        Raises:
            ValidationError: If status is invalid
        """
        if not isinstance(value, str):
            raise ValidationError("Status must be a string")

        value = value.lower().strip()

        if value not in valid_statuses:
            raise ValidationError(f"Invalid status (must be one of: {valid_statuses})")

        return value

    @classmethod
    def validate_pagination(
        cls,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> tuple[int, int]:
        """
        Validate pagination parameters.

        Args:
            limit: Number of items to return
            offset: Number of items to skip

        Returns:
            (validated_limit, validated_offset)

        Raises:
            ValidationError: If parameters are invalid
        """
        # Default values
        default_limit = 20
        max_limit = 100

        # Validate limit
        if limit is None:
            limit = default_limit
        else:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                raise ValidationError("Limit must be an integer")

            if limit < 1:
                raise ValidationError("Limit must be positive")
            if limit > max_limit:
                raise ValidationError(f"Limit too large (max {max_limit})")

        # Validate offset
        if offset is None:
            offset = 0
        else:
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                raise ValidationError("Offset must be an integer")

            if offset < 0:
                raise ValidationError("Offset must be non-negative")

        return limit, offset

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename

        Raises:
            ValidationError: If filename is invalid
        """
        if not isinstance(filename, str):
            raise ValidationError("Filename must be a string")

        # Remove path components
        filename = filename.replace("\\", "/")
        filename = filename.split("/")[-1]

        # Remove dangerous characters
        filename = re.sub(r"[^\w\s.-]", "", filename)

        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = name[:250] + ("." + ext if ext else "")

        if not filename:
            raise ValidationError("Invalid filename")

        return filename
