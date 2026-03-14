"""Core data types for AgentVault."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class Entry(BaseModel):
    """A single entry in the vault with metadata."""

    key: str
    value: Any
    agent: str | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class WatchEvent(BaseModel):
    """Event emitted when a key changes."""

    key: str
    new_value: Any
    old_value: Any | None = None
    agent: str | None = None
    version: int
    event_type: Literal["put", "delete"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    _trigger_depth: int = 0


class AgentContract(BaseModel):
    """Declares what keys an agent produces and consumes, with expected types."""

    name: str
    produces: dict[str, Any] = Field(default_factory=dict)
    consumes: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
