"""Pydantic-схемы API обратной связи."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class FeedbackOut(BaseModel):
    id: int
    type: str
    status: str
    created_at: Optional[datetime] = None


class FeedbackListItem(BaseModel):
    id: int
    type: str
    status: str
    text: str
    has_media: bool = False
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None


class FeedbackListOut(BaseModel):
    items: List[FeedbackListItem]
    total: int


class FeedbackDetailOut(BaseModel):
    id: int
    type: str
    status: str
    text: str
    source: str
    media_ids: List[int] = []
    reply: Optional[str] = None
    replied_at: Optional[datetime] = None
    author_name: Optional[str] = None
    author_phone: Optional[str] = None
    created_at: Optional[datetime] = None


class FeedbackUpdate(BaseModel):
    status: Optional[str] = None
    reply: Optional[str] = None
