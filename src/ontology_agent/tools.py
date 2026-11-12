"""Tool functions over the ontology.

One definition serves two transports: ``mcp_server.py`` registers these on an MCP
server (the production path), and the tests wrap them as in-process Agent
Framework tools so side effects can be asserted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from .ontology import Obj, Ontology

READ_TOOLS = ("list_object_types", "search_objects", "get_object", "get_linked_objects", "leases_expiring")
ACTION_TOOLS = ("create_work_order", "flag_lease_renewal")

ObjectType = Annotated[str, Field(description="One of: property, unit, tenant, lease, work_order")]


def build_tool_functions(ont: Ontology) -> dict[str, Callable[..., Any]]:
    def list_object_types() -> list[str]:
        """List the object types available in the property ontology."""
        return ["property", "unit", "tenant", "lease", "work_order"]

    def search_objects(
        object_type: ObjectType,
        query: Annotated[str, Field(description="Text to match against any field; empty returns all")] = "",
    ) -> list[Obj]:
        """Search objects of one type by free text."""
        return ont.search(object_type, query)

    def get_object(
        object_type: ObjectType, object_id: Annotated[str, Field(description="Object id, e.g. U-003")]
    ) -> Obj:
        """Fetch one object by type and id."""
        return ont.get(object_type, object_id)

    def get_linked_objects(
        object_type: ObjectType,
        object_id: Annotated[str, Field(description="Id of the starting object")],
        target_type: ObjectType,
    ) -> list[Obj]:
        """Follow a link from one object to related objects, e.g. unit -> lease or lease -> tenant."""
        return ont.linked(object_type, object_id, target_type)

    def leases_expiring(
        within_days: Annotated[int, Field(ge=1, le=730, description="Look-ahead window in days")],
    ) -> list[Obj]:
        """List leases ending within the next N days of the ontology's as-of date."""
        return ont.leases_expiring(within_days)

    def create_work_order(
        unit_id: Annotated[str, Field(description="Unit id, e.g. U-003")],
        category: Annotated[str, Field(description="plumbing, electrical, hvac or general")],
        priority: Annotated[str, Field(description="low, medium or high")],
        description: Annotated[str, Field(description="What is wrong, in one or two sentences")],
    ) -> Obj:
        """ACTION: create a maintenance work order. Requires human approval."""
        return ont.create_work_order(unit_id, category, priority, description)

    def flag_lease_renewal(
        lease_id: Annotated[str, Field(description="Lease id, e.g. L-004")],
        note: Annotated[str, Field(description="Why the lease is being flagged")],
    ) -> Obj:
        """ACTION: flag a lease for renewal follow-up by the leasing team. Requires human approval."""
        return ont.flag_lease_renewal(lease_id, note)

    fns: list[Callable[..., Any]] = [
        list_object_types,
        search_objects,
        get_object,
        get_linked_objects,
        leases_expiring,
        create_work_order,
        flag_lease_renewal,
    ]
    return {fn.__name__: fn for fn in fns}
