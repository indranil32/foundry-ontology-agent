from __future__ import annotations

import json

import pytest

from ontology_agent.clients import Step, say
from ontology_agent.config import Settings
from ontology_agent.ontology import Ontology


@pytest.fixture
def ontology() -> Ontology:
    return Ontology.load()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        project_endpoint=None,
        model_deployment="test",
        price_input_per_m=1.0,
        price_output_per_m=4.0,
        max_latency_ms=15000,
        max_cost_usd_per_request=0.02,
    )


def triage(route: str, confidence: float = 0.9) -> Step:
    return say(json.dumps({"route": route, "reason": "test", "confidence": confidence}))
