"""
Localization utilities for Request Service
UK Management Bot - Request Management System

Provides centralized localization for notification templates and messages.
"""

from typing import Dict, Any, Optional
from enum import Enum


class SupportedLanguage(str, Enum):
    """Supported languages"""
    RUSSIAN = "ru"
    UZBEK = "uz"


class NotificationTemplates:
    """
    Centralized notification templates for all supported languages
    """

    # Assignment notification templates
    ASSIGNMENT_EXECUTOR = {
        SupportedLanguage.RUSSIAN: "📋 Вам назначена заявка #{request_number}\n📝 {title}\n📍 {address}\n⚡ Приоритет: {priority}",
        SupportedLanguage.UZBEK: "📋 Sizga № {request_number} ariza tayinlandi\n📝 {title}\n📍 {address}\n⚡ Muhimlik: {priority}"
    }

    ASSIGNMENT_CREATOR = {
        SupportedLanguage.RUSSIAN: "✅ Вашей заявке #{request_number} назначен исполнитель\n👷 Исполнитель ID: {executor_id}",
        SupportedLanguage.UZBEK: "✅ #{request_number} arizangizga ijrochi tayinlandi\n👷 Ijrochi ID: {executor_id}"
    }

    ASSIGNMENT_ASSIGNER = {
        SupportedLanguage.RUSSIAN: "📊 Заявка #{request_number} назначена исполнителю {executor_id}\n📝 {title}",
        SupportedLanguage.UZBEK: "📊 № {request_number} ariza {executor_id} ijrochiga tayinlandi\n📝 {title}"
    }


class LocalizationService:
    """
    Service for handling localization of notification templates
    """

    def __init__(self):
        self.default_language = SupportedLanguage.RUSSIAN

    def get_assignment_notification_templates(
        self,
        request_data: Dict[str, Any],
        assignment_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, str]]:
        """
        Generate localized assignment notification templates

        Args:
            request_data: Request information
            assignment_data: Assignment information

        Returns:
            Dictionary with templates for different recipient types in all languages
        """

        # Template variables
        template_vars = {
            "request_number": request_data.get("request_number", ""),
            "title": request_data.get("title", ""),
            "address": request_data.get("address", ""),
            "priority": request_data.get("priority", ""),
            "executor_id": assignment_data.get("assigned_user_id", "")
        }

        return {
            "executor": {
                SupportedLanguage.RUSSIAN: NotificationTemplates.ASSIGNMENT_EXECUTOR[SupportedLanguage.RUSSIAN].format(**template_vars),
                SupportedLanguage.UZBEK: NotificationTemplates.ASSIGNMENT_EXECUTOR[SupportedLanguage.UZBEK].format(**template_vars)
            },
            "creator": {
                SupportedLanguage.RUSSIAN: NotificationTemplates.ASSIGNMENT_CREATOR[SupportedLanguage.RUSSIAN].format(**template_vars),
                SupportedLanguage.UZBEK: NotificationTemplates.ASSIGNMENT_CREATOR[SupportedLanguage.UZBEK].format(**template_vars)
            },
            "assigner": {
                SupportedLanguage.RUSSIAN: NotificationTemplates.ASSIGNMENT_ASSIGNER[SupportedLanguage.RUSSIAN].format(**template_vars),
                SupportedLanguage.UZBEK: NotificationTemplates.ASSIGNMENT_ASSIGNER[SupportedLanguage.UZBEK].format(**template_vars)
            }
        }

    def get_template(
        self,
        template_key: str,
        language: SupportedLanguage = None,
        **kwargs
    ) -> str:
        """
        Get a specific template with variables substituted

        Args:
            template_key: Key for the template (e.g., 'assignment_executor')
            language: Language code, defaults to default_language
            **kwargs: Template variables for substitution

        Returns:
            Formatted template string
        """
        if language is None:
            language = self.default_language

        template_map = {
            "assignment_executor": NotificationTemplates.ASSIGNMENT_EXECUTOR,
            "assignment_creator": NotificationTemplates.ASSIGNMENT_CREATOR,
            "assignment_assigner": NotificationTemplates.ASSIGNMENT_ASSIGNER
        }

        template_dict = template_map.get(template_key)
        if not template_dict:
            raise ValueError(f"Unknown template key: {template_key}")

        template = template_dict.get(language)
        if not template:
            # Fallback to default language
            template = template_dict.get(self.default_language)
            if not template:
                raise ValueError(f"No template found for key: {template_key}")

        return template.format(**kwargs)

    def is_language_supported(self, language: str) -> bool:
        """
        Check if language is supported

        Args:
            language: Language code to check

        Returns:
            True if language is supported
        """
        try:
            SupportedLanguage(language)
            return True
        except ValueError:
            return False


# Global localization service instance
localization_service = LocalizationService()


def get_localized_templates(
    request_data: Dict[str, Any],
    assignment_data: Dict[str, Any]
) -> Dict[str, Dict[str, str]]:
    """
    Convenience function to get localized assignment templates

    Args:
        request_data: Request information
        assignment_data: Assignment information

    Returns:
        Dictionary with templates for different recipient types in all languages
    """
    return localization_service.get_assignment_notification_templates(
        request_data, assignment_data
    )