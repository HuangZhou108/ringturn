from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryKind = Literal["preference", "constraint", "feedback", "instruction", "history"]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: MemoryKind = "preference"
    importance: float = Field(default=0.7, ge=0, le=1)
    confidence: float = Field(default=0.9, ge=0, le=1)
    pinned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    importance: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    pinned: bool | None = None


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    profile_id: int | None = None
    source: str = Field(default="manual", min_length=1, max_length=255)
