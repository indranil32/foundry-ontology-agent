"""Structured outputs and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Route = Literal["maintenance", "leasing", "general"]


class TriageDecision(BaseModel):
    """Structured output of the triage agent."""

    route: Route
    reason: str = Field(description="One sentence explaining the routing choice")
    confidence: float = Field(default=1.0, ge=0, le=1)


@dataclass
class ApprovalRecord:
    tool: str
    arguments: dict[str, Any]
    approved: bool


@dataclass
class AssistantResult:
    route: Route
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    prompt_versions: dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
