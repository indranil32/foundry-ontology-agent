"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_endpoint: str | None
    model_deployment: str
    # Token prices in USD per 1M tokens. Set them from your Azure price sheet for the
    # deployed model; the defaults are placeholders used only for relative comparisons.
    price_input_per_m: float
    price_output_per_m: float
    max_latency_ms: float
    max_cost_usd_per_request: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            project_endpoint=os.environ.get("FOUNDRY_PROJECT_ENDPOINT"),
            model_deployment=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "chat-model"),
            price_input_per_m=float(os.environ.get("PRICE_INPUT_PER_M", "0.40")),
            price_output_per_m=float(os.environ.get("PRICE_OUTPUT_PER_M", "1.60")),
            max_latency_ms=float(os.environ.get("EVAL_MAX_LATENCY_MS", "15000")),
            max_cost_usd_per_request=float(os.environ.get("EVAL_MAX_COST_USD", "0.02")),
        )

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.price_input_per_m + output_tokens * self.price_output_per_m) / 1_000_000
