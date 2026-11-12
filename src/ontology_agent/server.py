"""HTTP API for Azure Container Apps.

POST /ask                                -> answer, or pending approvals for actions
POST /conversations/{id}/decisions       -> approve/reject pending actions and resume
GET  /health

Human-in-the-loop over HTTP: the agent stops at any action and returns it as a
pending approval; nothing is written until a person posts a decision.

This demo keeps conversations and the ontology in memory, so run one replica.
Production would persist sessions (e.g. Cosmos DB) and reach the ontology over
remote MCP instead of in-process tools.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agents import Conversation, PropertyOpsAssistant, in_process_tools
from .clients import build_foundry_client
from .config import Settings
from .ontology import Ontology
from .telemetry import setup_telemetry


class AskRequest(BaseModel):
    question: str


class Decisions(BaseModel):
    decisions: dict[str, bool]


def _view(conv: Conversation) -> dict[str, Any]:
    body: dict[str, Any] = {"conversation_id": conv.id, "route": conv.route, "triage_reason": conv.triage.reason}
    if conv.pending:
        body["status"] = "awaiting_approval"
        body["pending"] = [{"call_id": p.call_id, "tool": p.tool, "arguments": p.arguments} for p in conv.pending]
    elif conv.result:
        r = conv.result
        body.update(
            status="completed",
            answer=r.answer,
            tool_calls=r.tool_calls,
            approvals=[{"tool": a.tool, "approved": a.approved} for a in r.approvals],
            tokens={"input": r.input_tokens, "output": r.output_tokens},
            estimated_cost_usd=r.estimated_cost_usd,
            latency_ms=round(r.latency_ms),
            prompt_versions=r.prompt_versions,
        )
    return body


def create_app(assistant: PropertyOpsAssistant | None = None) -> FastAPI:
    app = FastAPI(title="Property Operations Agent")
    conversations: dict[str, Conversation] = {}

    def get_assistant() -> PropertyOpsAssistant:
        nonlocal assistant
        if assistant is None:
            setup_telemetry()
            settings = Settings.from_env()
            assistant = PropertyOpsAssistant(
                build_foundry_client(settings), in_process_tools(Ontology.load()), settings
            )
        return assistant

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ask")
    async def ask(req: AskRequest) -> dict[str, Any]:
        conv = await get_assistant().begin(req.question)
        if conv.pending:
            conversations[conv.id] = conv
        return _view(conv)

    @app.post("/conversations/{conversation_id}/decisions")
    async def decide(conversation_id: str, body: Decisions) -> dict[str, Any]:
        conv = conversations.get(conversation_id)
        if conv is None:
            raise HTTPException(404, "Unknown or completed conversation")
        conv = await get_assistant().resume(conv, body.decisions)
        if not conv.pending:
            conversations.pop(conversation_id, None)
        return _view(conv)

    return app


app = create_app()
