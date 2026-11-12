"""Versioned prompts, stored as YAML next to the code and reviewed like code.

Pin a version per agent with ``PROMPT_VERSION_<AGENT>`` (e.g. ``PROMPT_VERSION_TRIAGE=v1``);
otherwise the highest version is used. The version is recorded on every trace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    agent: str
    version: str
    instructions: str


def available_versions(agent: str) -> list[str]:
    files = sorted((PROMPT_DIR / agent).glob("v*.yaml"), key=lambda p: int(p.stem[1:]))
    return [p.stem for p in files]


def load_prompt(agent: str, version: str | None = None) -> Prompt:
    versions = available_versions(agent)
    if not versions:
        raise FileNotFoundError(f"No prompts for agent '{agent}'")
    chosen = version or os.environ.get(f"PROMPT_VERSION_{agent.upper()}") or versions[-1]
    if chosen not in versions:
        raise ValueError(f"Prompt {agent}/{chosen} not found; available: {versions}")
    data = yaml.safe_load((PROMPT_DIR / agent / f"{chosen}.yaml").read_text())
    return Prompt(agent=agent, version=data["version"], instructions=data["instructions"].strip())
