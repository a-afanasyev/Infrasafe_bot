"""
Интеграции с внешними сервисами
"""
from typing import Optional
from uk_management_bot.integrations.media_client import MediaServiceClient
from uk_management_bot.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Глобальный экземпляр медиа-клиента
_media_client: Optional[MediaServiceClient] = None


def get_media_client() -> Optional[MediaServiceClient]:
    """
    Получить клиент медиа-сервиса

    Returns:
        MediaServiceClient или None если сервис отключен
    """
    global _media_client

    if not settings.MEDIA_SERVICE_ENABLED:
        return None

    if _media_client is None:
        try:
            _media_client = MediaServiceClient(
                base_url=settings.MEDIA_SERVICE_URL,
                timeout=settings.MEDIA_SERVICE_TIMEOUT
            )
            logger.info(f"Media Service клиент инициализирован: {settings.MEDIA_SERVICE_URL}")
        except Exception as e:
            logger.error(f"Ошибка инициализации Media Service клиента: {e}")
            return None

    return _media_client


async def close_media_client():
    """
    Закрыть клиент медиа-сервиса
    """
    global _media_client

    if _media_client is not None:
        try:
            await _media_client.close()
            logger.info("Media Service клиент закрыт")
        except Exception as e:
            logger.error(f"Ошибка закрытия Media Service клиента: {e}")
        finally:
            _media_client = None


__all__ = ['get_media_client', 'close_media_client', 'MediaServiceClient']
