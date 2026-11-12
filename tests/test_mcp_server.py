import pytest

from ontology_agent.mcp_server import create_server
from ontology_agent.ontology import Ontology
from ontology_agent.tools import ACTION_TOOLS, READ_TOOLS


@pytest.mark.asyncio
async def test_server_exposes_all_tools_with_safety_annotations(ontology: Ontology) -> None:
    server = create_server(ontology)
    tools = {t.name: t for t in await server.list_tools()}
    assert set(tools) == set(READ_TOOLS) | set(ACTION_TOOLS)
    for name in ACTION_TOOLS:
        assert tools[name].annotations is not None and tools[name].annotations.destructive_hint
    for name in READ_TOOLS:
        assert tools[name].annotations is not None and tools[name].annotations.read_only_hint
