"""Multi-agent orchestration: a triage router plus specialist agents with tools and human approval.

Flow for one request:
  1. Triage agent returns a structured ``TriageDecision`` (route + confidence).
  2. The chosen specialist runs with only the tools it needs (least privilege).
  3. Read tools run freely. Action tools pause the run and raise an approval request;
     a human (or policy) approves or rejects, and the run resumes.
  4. Tokens, cost, latency, tool calls and prompt versions are recorded on the result
     and on the request's trace span.
"""

from __future__ import annotations

import inspect
import os
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, AgentResponse, AgentSession, Content, MCPStdioTool, Message, tool
from pydantic import ValidationError

from .config import Settings
from .models import ApprovalRecord, AssistantResult, Route, TriageDecision
from .ontology import Ontology
from .prompts import Prompt, load_prompt
from .telemetry import tracer
from .tools import ACTION_TOOLS, READ_TOOLS, build_tool_functions

SPECIALIST_TOOLS: dict[Route, tuple[str, ...]] = {
    "maintenance": ("search_objects", "get_object", "get_linked_objects", "create_work_order"),
    "leasing": ("search_objects", "get_object", "get_linked_objects", "leases_expiring", "flag_lease_renewal"),
    "general": ("list_object_types", "search_objects", "get_object", "get_linked_objects"),
}
MIN_TRIAGE_CONFIDENCE = 0.5
MAX_APPROVAL_ROUNDS = 5

ToolsFactory = Callable[[tuple[str, ...]], list[Any]]
Approver = Callable[[str, dict[str, Any]], bool | Awaitable[bool]]


# ---- tool providers ----------------------------------------------------------


def mcp_tools(allowed: tuple[str, ...]) -> list[Any]:
    """Ontology tools over MCP (stdio). Swap for MCPStreamableHTTPTool to reach a remote server,
    e.g. an enterprise ontology such as Palantir Foundry exposed through MCP."""
    return [
        MCPStdioTool(
            name="ontology",
            command=sys.executable,
            args=["-m", "ontology_agent.mcp_server"],
            env=dict(os.environ),
            allowed_tools=list(allowed),
            approval_mode={
                "always_require_approval": list(ACTION_TOOLS),
                "never_require_approval": list(READ_TOOLS),
                "default": "always_require",  # anything unexpected needs a human
            },
        )
    ]


def in_process_tools(ontology: Ontology) -> ToolsFactory:
    """Same tools, called in-process on a shared ontology (tests, and the single-replica HTTP demo)."""
    functions = build_tool_functions(ontology)

    def factory(allowed: tuple[str, ...]) -> list[Any]:
        return [
            tool(functions[name], approval_mode="always_require" if name in ACTION_TOOLS else "never_require")
            for name in allowed
        ]

    return factory


def deny_all(name: str, arguments: dict[str, Any]) -> bool:
    """Safe default approver: propose actions, never execute them."""
    return False


# ---- conversation state -------------------------------------------------------


@dataclass
class PendingApproval:
    call_id: str
    tool: str
    arguments: dict[str, Any]
    request: Content


@dataclass
class Conversation:
    id: str
    question: str
    route: Route
    triage: TriageDecision
    agent: Agent[Any]
    session: AgentSession
    pending: list[PendingApproval] = field(default_factory=list)
    answer: str = ""
    result: AssistantResult | None = None
    started: float = field(default_factory=time.perf_counter)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[str] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)


class PropertyOpsAssistant:
    def __init__(
        self,
        client: Any,
        tools_factory: ToolsFactory,
        settings: Settings | None = None,
        prompt_versions: Mapping[str, str] | None = None,
    ) -> None:
        self.client = client
        self.tools_factory = tools_factory
        self.settings = settings or Settings.from_env()
        versions = dict(prompt_versions or {})
        self.prompts: dict[str, Prompt] = {
            a: load_prompt(a, versions.get(a)) for a in ("triage", "maintenance", "leasing", "general")
        }

    @property
    def prompt_versions(self) -> dict[str, str]:
        return {agent: p.version for agent, p in self.prompts.items()}

    # One call, approvals decided by `approver` (CLI, evals, tests).
    async def ask(self, question: str, approver: Approver = deny_all) -> AssistantResult:
        with tracer.start_as_current_span("property_ops.request") as span:
            conv = await self._triage(question)
            async with conv.agent:
                self._absorb(conv, await conv.agent.run(question, session=conv.session))
                rounds = 0
                while conv.pending and rounds < MAX_APPROVAL_ROUNDS:
                    rounds += 1
                    decisions = {}
                    for item in conv.pending:
                        verdict = approver(item.tool, item.arguments)
                        decisions[item.call_id] = bool(await verdict) if inspect.isawaitable(verdict) else bool(verdict)
                    await self._resume(conv, decisions)
            result = self._finish(conv)
            self._annotate(span, result)
            return result

    # Two-step use for HTTP: begin() may stop at pending approvals; resume() continues.
    async def begin(self, question: str) -> Conversation:
        with tracer.start_as_current_span("property_ops.begin"):
            conv = await self._triage(question)
            self._absorb(conv, await conv.agent.run(question, session=conv.session))
            if not conv.pending:
                conv.result = self._finish(conv)
            return conv

    async def resume(self, conv: Conversation, decisions: Mapping[str, bool]) -> Conversation:
        with tracer.start_as_current_span("property_ops.resume"):
            await self._resume(conv, decisions)
            if not conv.pending:
                conv.result = self._finish(conv)
            return conv

    # ---- internals ---------------------------------------------------------

    async def _triage(self, question: str) -> Conversation:
        triage_agent = Agent(client=self.client, name="triage", instructions=self.prompts["triage"].instructions)
        response = await triage_agent.run(question, options={"response_format": TriageDecision})
        decision = self._parse_triage(response)
        route: Route = decision.route if decision.confidence >= MIN_TRIAGE_CONFIDENCE else "general"
        specialist = Agent(
            client=self.client,
            name=route,
            instructions=self.prompts[route].instructions,
            tools=self.tools_factory(SPECIALIST_TOOLS[route]),
        )
        conv = Conversation(
            id=uuid.uuid4().hex,
            question=question,
            route=route,
            triage=decision,
            agent=specialist,
            session=specialist.create_session(),
        )
        self._count_usage(conv, response)
        return conv

    @staticmethod
    def _parse_triage(response: AgentResponse[Any]) -> TriageDecision:
        """Malformed structured output must not crash the request: fall back to the read-only agent."""
        try:
            value = response.value
        except ValidationError:
            value = None
        if isinstance(value, TriageDecision):
            return value
        return TriageDecision(route="general", reason="Unparseable triage output", confidence=0.0)

    async def _resume(self, conv: Conversation, decisions: Mapping[str, bool]) -> None:
        replies = []
        for item in conv.pending:
            approved = bool(decisions.get(item.call_id, False))  # missing decision = rejected
            conv.approvals.append(ApprovalRecord(tool=item.tool, arguments=item.arguments, approved=approved))
            replies.append(item.request.to_function_approval_response(approved))
        conv.pending = []
        self._absorb(conv, await conv.agent.run(Message(role="user", contents=replies), session=conv.session))

    def _absorb(self, conv: Conversation, response: AgentResponse[Any]) -> None:
        self._count_usage(conv, response)
        for message in response.messages:
            for content in message.contents:
                if content.type == "function_call" and content.name:
                    conv.tool_calls.append(content.name)
        for request in response.user_input_requests:
            call = request.function_call
            if call is None or call.name is None:
                continue
            arguments = call.parse_arguments() or {}
            conv.pending.append(
                PendingApproval(
                    call_id=call.call_id or uuid.uuid4().hex, tool=call.name, arguments=dict(arguments), request=request
                )
            )
        conv.answer = response.text

    @staticmethod
    def _count_usage(conv: Conversation, response: AgentResponse[Any]) -> None:
        usage = getattr(response, "usage_details", None) or {}
        conv.input_tokens += int(usage.get("input_token_count") or 0)
        conv.output_tokens += int(usage.get("output_token_count") or 0)

    def _finish(self, conv: Conversation) -> AssistantResult:
        return AssistantResult(
            route=conv.route,
            answer=conv.answer,
            tool_calls=list(conv.tool_calls),
            approvals=list(conv.approvals),
            prompt_versions=self.prompt_versions,
            latency_ms=(time.perf_counter() - conv.started) * 1000,
            input_tokens=conv.input_tokens,
            output_tokens=conv.output_tokens,
            estimated_cost_usd=self.settings.cost(conv.input_tokens, conv.output_tokens),
        )

    @staticmethod
    def _annotate(span: Any, result: AssistantResult) -> None:
        span.set_attribute("ops.route", result.route)
        span.set_attribute("ops.tool_calls", ",".join(result.tool_calls))
        span.set_attribute("ops.approvals.requested", len(result.approvals))
        span.set_attribute("ops.approvals.granted", sum(a.approved for a in result.approvals))
        span.set_attribute("ops.tokens.input", result.input_tokens)
        span.set_attribute("ops.tokens.output", result.output_tokens)
        span.set_attribute("ops.cost_usd", result.estimated_cost_usd)
        span.set_attribute("ops.latency_ms", result.latency_ms)
        for agent, version in result.prompt_versions.items():
            span.set_attribute(f"ops.prompt_version.{agent}", version)
