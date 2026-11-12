"""End-to-end agent loop with a scripted model: routing, tools, approvals, cost accounting."""

from __future__ import annotations

import sys

import pytest
from conftest import triage

from ontology_agent.agents import PropertyOpsAssistant, deny_all, in_process_tools, mcp_tools
from ontology_agent.clients import ScriptedChatClient, call, say
from ontology_agent.config import Settings
from ontology_agent.ontology import Ontology

pytestmark = pytest.mark.asyncio


def approve_all(name: str, arguments: dict[str, object]) -> bool:
    return True


async def test_read_only_question_routes_and_answers(ontology: Ontology, settings: Settings) -> None:
    client = ScriptedChatClient(
        [
            triage("leasing"),
            call("get_linked_objects", "c1", object_type="unit", object_id="U-002", target_type="lease"),
            say("Unit U-002 is leased under L-002."),
        ]
    )
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask("Who leases U-002?")
    assert result.route == "leasing"
    assert result.tool_calls == ["get_linked_objects"]
    assert result.approvals == []
    assert "L-002" in result.answer
    assert client.remaining == 0


async def test_action_executes_only_after_approval(ontology: Ontology, settings: Settings) -> None:
    before = len(ontology.search("work_order"))
    client = ScriptedChatClient(
        [
            triage("maintenance"),
            call("get_object", "c1", object_type="unit", object_id="U-002"),
            call(
                "create_work_order",
                "c2",
                unit_id="U-002",
                category="plumbing",
                priority="high",
                description="Leaking pipe",
            ),
            say("Created a high-priority plumbing work order for U-002."),
        ]
    )
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask(
        "Leaking pipe in U-002, raise a work order", approver=approve_all
    )
    assert [(a.tool, a.approved) for a in result.approvals] == [("create_work_order", True)]
    assert len(ontology.search("work_order")) == before + 1
    assert ontology.audit_log[-1]["action"] == "create_work_order"


async def test_rejected_action_is_never_written(ontology: Ontology, settings: Settings) -> None:
    before = len(ontology.search("work_order"))
    client = ScriptedChatClient(
        [
            triage("maintenance"),
            call(
                "create_work_order",
                "c1",
                unit_id="U-002",
                category="plumbing",
                priority="high",
                description="Leaking pipe",
            ),
            say("The work order was not approved, so nothing was created."),
        ]
    )
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask(
        "Raise a work order for U-002", approver=deny_all
    )
    assert [(a.tool, a.approved) for a in result.approvals] == [("create_work_order", False)]
    assert len(ontology.search("work_order")) == before
    assert ontology.audit_log == []


async def test_low_confidence_falls_back_to_read_only_general(ontology: Ontology, settings: Settings) -> None:
    client = ScriptedChatClient([triage("maintenance", confidence=0.2), say("Could you clarify the unit?")])
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask("Something is off")
    assert result.route == "general"


async def test_unparseable_triage_falls_back_to_general(ontology: Ontology, settings: Settings) -> None:
    client = ScriptedChatClient([say("not json"), say("Please rephrase.")])
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask("??")
    assert result.route == "general"


async def test_specialists_only_get_their_own_tools(ontology: Ontology, settings: Settings) -> None:
    # The general agent is read-only, so an action call is refused rather than executed.
    client = ScriptedChatClient(
        [
            triage("general"),
            call("create_work_order", "c1", unit_id="U-001", category="general", priority="low", description="x"),
            say("I can't do that here; the maintenance specialist handles work orders."),
        ]
    )
    await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask("x", approver=approve_all)
    assert ontology.audit_log == []


async def test_tokens_and_cost_are_accounted(ontology: Ontology, settings: Settings) -> None:
    client = ScriptedChatClient([triage("general"), say("There are 3 properties.")])
    result = await PropertyOpsAssistant(client, in_process_tools(ontology), settings).ask("How many properties?")
    assert (result.input_tokens, result.output_tokens) == (400, 80)  # 2 scripted turns x (200 in, 40 out)
    assert result.estimated_cost_usd == pytest.approx((400 * 1.0 + 80 * 4.0) / 1_000_000)
    assert result.prompt_versions["triage"] == "v2"


@pytest.mark.skipif(sys.platform == "win32", reason="stdio subprocess test")
async def test_agent_reaches_ontology_over_mcp(settings: Settings) -> None:
    client = ScriptedChatClient(
        [
            triage("leasing"),
            call("leases_expiring", "c1", within_days=90),
            say("Several leases expire within 90 days."),
        ]
    )
    result = await PropertyOpsAssistant(client, mcp_tools, settings).ask("Which leases expire in 90 days?")
    assert result.tool_calls == ["leases_expiring"]
    assert result.approvals == []
