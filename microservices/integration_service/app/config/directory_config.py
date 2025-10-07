"""
Directory API Configuration
Task 9.4A - Building Directory Integration

Configuration for Building Directory API client
"""

from pydantic_settings import BaseSettings
from typing import Optional


class DirectoryConfig(BaseSettings):
    """Configuration for Building Directory API"""

    # Directory API settings
    DIRECTORY_API_URL: str = "http://localhost:8001"
    DIRECTORY_API_TIMEOUT: int = 30
    DIRECTORY_API_RETRIES: int = 3
    DIRECTORY_API_RETRY_DELAY: float = 1.0

    # Cache settings
    DIRECTORY_CACHE_ENABLED: bool = True
    DIRECTORY_CACHE_TTL_BUILDING: int = 3600  # 1 hour for building details
    DIRECTORY_CACHE_TTL_LIST: int = 300  # 5 minutes for building lists
    DIRECTORY_CACHE_TTL_COORDINATES: int = 86400  # 24 hours for coordinates

    # Management Company ID (tenant isolation)
    MANAGEMENT_COMPANY_ID: str = "00000000-0000-0000-0000-000000000001"

    # Google Maps API (for geocoding fallback)
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_MAPS_ENABLED: bool = False
    GOOGLE_MAPS_TIMEOUT: int = 10

    # Performance settings
    MAX_CONCURRENT_REQUESTS: int = 10
    BATCH_SIZE: int = 50

    class Config:
        env_file = ".env"
        env_prefix = "DIRECTORY_"
        case_sensitive = True


# Global config instance
directory_config = DirectoryConfig()
