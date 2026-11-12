"""MCP server exposing the property ontology to agents.

Run standalone:  python -m ontology_agent.mcp_server            (stdio)
                 python -m ontology_agent.mcp_server --http       (streamable HTTP)

Read tools are safe to call freely. Action tools are annotated as destructive;
the agent side additionally requires human approval before calling them.
"""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .ontology import DATA_PATH, Ontology
from .tools import ACTION_TOOLS, build_tool_functions


def create_server(ontology: Ontology | None = None) -> MCPServer:
    ont = ontology or Ontology.load(os.environ.get("ONTOLOGY_PATH", DATA_PATH))
    server = MCPServer(
        name="property-ontology",
        instructions="Typed property-operations ontology: properties, units, tenants, leases, work orders.",
    )
    for name, fn in build_tool_functions(ont).items():
        is_action = name in ACTION_TOOLS
        server.add_tool(fn, annotations=ToolAnnotations(read_only_hint=not is_action, destructive_hint=is_action))
    return server


def main() -> None:
    server = create_server()
    server.run("streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
