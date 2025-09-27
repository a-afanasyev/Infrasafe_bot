"""
Request Service - Adapters Module
UK Management Bot - Request Management System

Adapters for external system integration and migration support.
"""

from .dual_write_adapter import DualWriteAdapter

__all__ = ["DualWriteAdapter"]