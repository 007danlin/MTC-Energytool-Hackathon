"""Minimal data contracts shared by retrieval and generation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    role: str
    content: str

    def __post_init__(self):
        if self.role not in ("user", "assistant") or not isinstance(self.content, str):
            raise ValueError("Only user/assistant text messages are accepted")
        if not self.content.strip():
            raise ValueError("Message must not be empty")


@dataclass(frozen=True)
class Fragment:
    document_id: str
    chunk_id: str
    text: str
    score: float = 0.0

    @property
    def source_id(self):
        return self.document_id + "#" + self.chunk_id
