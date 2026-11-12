"""HTTP human-in-the-loop: the API pauses at an action and resumes only on a human decision."""

from __future__ import annotations

from conftest import triage
from fastapi.testclient import TestClient

from ontology_agent.agents import PropertyOpsAssistant, in_process_tools
from ontology_agent.clients import ScriptedChatClient, call, say
from ontology_agent.config import Settings
from ontology_agent.ontology import Ontology
from ontology_agent.server import create_app


def _client(ontology: Ontology, settings: Settings, final: str) -> TestClient:
    model = ScriptedChatClient(
        [
            triage("maintenance"),
            call(
                "create_work_order",
                "c1",
                unit_id="U-005",
                category="hvac",
                priority="medium",
                description="AC not cooling",
            ),
            say(final),
        ]
    )
    return TestClient(create_app(PropertyOpsAssistant(model, in_process_tools(ontology), settings)))


def test_action_waits_for_human_then_executes(ontology: Ontology, settings: Settings) -> None:
    api = _client(ontology, settings, "Work order created for U-005.")
    first = api.post("/ask", json={"question": "AC not cooling in U-005"}).json()
    assert first["status"] == "awaiting_approval"
    assert first["pending"][0]["tool"] == "create_work_order"
    assert ontology.audit_log == []  # nothing written yet

    call_id = first["pending"][0]["call_id"]
    done = api.post(f"/conversations/{first['conversation_id']}/decisions", json={"decisions": {call_id: True}}).json()
    assert done["status"] == "completed"
    assert done["approvals"] == [{"tool": "create_work_order", "approved": True}]
    assert ontology.audit_log[-1]["action"] == "create_work_order"


def test_rejection_and_unknown_conversation(ontology: Ontology, settings: Settings) -> None:
    api = _client(ontology, settings, "Not approved; nothing was created.")
    first = api.post("/ask", json={"question": "AC not cooling in U-005"}).json()
    done = api.post(f"/conversations/{first['conversation_id']}/decisions", json={"decisions": {}}).json()
    assert done["approvals"] == [{"tool": "create_work_order", "approved": False}]
    assert ontology.audit_log == []
    assert api.post("/conversations/nope/decisions", json={"decisions": {}}).status_code == 404
    assert api.get("/health").json() == {"status": "ok"}
