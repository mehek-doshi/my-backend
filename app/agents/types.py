"""Data carried between agents in the discovery pipeline."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class Candidate:
    """A possible technology topic while it moves through the pipeline. Nothing here is trusted yet."""

    title: str
    url: str
    raw_summary: str = ""
    published_at: datetime | None = None
    source_id: uuid.UUID | None = None
    source_name: str = ""
    # filled by the extraction agent
    page_text: str = ""
    page: dict[str, Any] = field(default_factory=dict)
    # filled by enrichment / classification
    summary: str = ""
    llm_category: str = ""
    category_id: uuid.UUID | None = None
    category_name: str = ""
    suggested_use_case: str = ""
    low_cost: bool = False
    # filled by dedup / guardrails / verification
    duplicate_of: uuid.UUID | None = None
    possible_duplicate_of: uuid.UUID | None = None
    similarity: float = 0.0
    flags: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    guardrail: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    verification: dict[str, Any] = field(default_factory=dict)

    @property
    def text_for_analysis(self) -> str:
        return " ".join(p for p in (self.title, self.raw_summary, self.page_text) if p)


class EnrichmentOutput(BaseModel):
    """The only shape an LLM reply is allowed to have. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=10, max_length=600)
    category: str = Field(default="", max_length=100)
    suggested_use_case: str = Field(default="", max_length=600)
    low_cost_simulation: bool = False
