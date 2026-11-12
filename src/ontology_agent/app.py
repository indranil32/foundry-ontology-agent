"""Command-line entry point.

    python -m ontology_agent.app "Is unit U-004 occupied, and by whom?"
    python -m ontology_agent.app --approve "Raise a high-priority plumbing work order for U-002: leaking pipe"

Uses the Foundry model configured in .env and the ontology over MCP. Actions are
shown to you for approval in the terminal unless --approve or --deny is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from .agents import PropertyOpsAssistant, mcp_tools
from .clients import build_foundry_client
from .config import Settings
from .telemetry import setup_telemetry


def _console_approver(mode: str | None):  # type: ignore[no-untyped-def]
    def approve(name: str, arguments: dict[str, Any]) -> bool:
        if mode is not None:
            return mode == "approve"
        print(f"\nApproval needed: {name}\n{json.dumps(arguments, indent=2)}")
        return input("Approve? [y/N] ").strip().lower() == "y"

    return approve


async def run(question: str, mode: str | None) -> None:
    from dotenv import load_dotenv

    load_dotenv()
    setup_telemetry()
    settings = Settings.from_env()
    assistant = PropertyOpsAssistant(build_foundry_client(settings), mcp_tools, settings)
    result = await assistant.ask(question, approver=_console_approver(mode))
    print(f"\n[{result.route}] {result.answer}")
    print(f"\ntools: {result.tool_calls}  approvals: {[(a.tool, a.approved) for a in result.approvals]}")
    print(
        f"tokens: {result.input_tokens} in / {result.output_tokens} out  "
        f"cost: ${result.estimated_cost_usd:.5f}  latency: {result.latency_ms:.0f} ms  "
        f"prompts: {result.prompt_versions}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--approve", action="store_const", const="approve", dest="mode")
    group.add_argument("--deny", action="store_const", const="deny", dest="mode")
    args = parser.parse_args()
    asyncio.run(run(args.question, args.mode))


if __name__ == "__main__":
    main()
