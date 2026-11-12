"""Chat clients: Microsoft Foundry for real runs, a scripted client for tests and offline CI."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
    UsageDetails,
)

from .config import Settings


def build_foundry_client(settings: Settings) -> Any:
    """Chat client for a model deployed in a Microsoft Foundry project.

    Auth uses Entra ID (DefaultAzureCredential): managed identity in Azure Container Apps,
    ``az login`` locally. No API keys are stored in code or config.
    """
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    if not settings.project_endpoint:
        raise RuntimeError("Set FOUNDRY_PROJECT_ENDPOINT (or use --offline for scripted runs)")
    return FoundryChatClient(
        project_endpoint=settings.project_endpoint,
        model=settings.model_deployment,
        credential=DefaultAzureCredential(),
    )


@dataclass
class Step:
    """One scripted model turn: what the 'model' returns, plus token usage to report."""

    contents: Sequence[Content]
    input_tokens: int = 200
    output_tokens: int = 40


@dataclass
class _Script:
    steps: list[Step]
    seen: list[Sequence[Message]] = field(default_factory=list)


class ScriptedChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Deterministic stand-in for an LLM.

    It replays scripted turns (tool calls, then text) so the full agent loop — tool
    execution, MCP transport, approval gates, structured output parsing, tracing and
    cost accounting — runs in CI without model calls or credentials. It tests the
    plumbing, not model quality; live evals against Foundry test the model.
    """

    def __init__(self, steps: Sequence[Step] | Callable[[], Sequence[Step]]) -> None:
        super().__init__()
        initial = steps() if callable(steps) else steps
        self._script = _Script(steps=list(initial))

    @property
    def remaining(self) -> int:
        return len(self._script.steps)

    async def _respond(self, messages: Sequence[Message]) -> ChatResponse:
        self._script.seen.append(list(messages))
        if not self._script.steps:
            raise RuntimeError("ScriptedChatClient ran out of scripted steps")
        step = self._script.steps.pop(0)
        usage = UsageDetails(
            input_token_count=step.input_tokens,
            output_token_count=step.output_tokens,
            total_token_count=step.input_tokens + step.output_tokens,
        )
        return ChatResponse(messages=[Message(role="assistant", contents=list(step.contents))], usage_details=usage)

    def _inner_get_response(self, *, messages: Sequence[Message], stream: bool, options: Any, **kwargs: Any) -> Any:
        return self._respond(messages)


def call(name: str, call_id: str, **arguments: Any) -> Step:
    return Step([Content.from_function_call(call_id=call_id, name=name, arguments=arguments)])


def say(text: str) -> Step:
    return Step([Content.from_text(text)])
