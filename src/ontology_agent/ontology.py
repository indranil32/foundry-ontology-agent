"""A small, Palantir-style ontology: typed objects, links between them, and audited actions.

The agent never touches this store directly. It reaches it through MCP tools
(see ``mcp_server.py``), the same way a production agent would reach an
enterprise ontology such as Palantir Foundry.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / "data" / "ontology.json"

# object type -> collection name in the data file
OBJECT_TYPES: dict[str, str] = {
    "property": "properties",
    "unit": "units",
    "tenant": "tenants",
    "lease": "leases",
    "work_order": "work_orders",
}

# (source type, target type) -> foreign-key field on the source object
LINKS: dict[tuple[str, str], str] = {
    ("unit", "property"): "property_id",
    ("lease", "unit"): "unit_id",
    ("lease", "tenant"): "tenant_id",
    ("work_order", "unit"): "unit_id",
}

WORK_ORDER_CATEGORIES = ("plumbing", "electrical", "hvac", "general")
PRIORITIES = ("low", "medium", "high")

Obj = dict[str, Any]


class OntologyError(ValueError):
    """Raised for unknown objects or invalid actions. The message is shown to the agent."""


class Ontology:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = copy.deepcopy(data)
        self.as_of = dt.date.fromisoformat(self._data["as_of"])
        self.audit_log: list[dict[str, Any]] = []

    @classmethod
    def load(cls, path: Path | str = DATA_PATH) -> Ontology:
        return cls(json.loads(Path(path).read_text()))

    # ---- reads -------------------------------------------------------------

    def _collection(self, object_type: str) -> list[Obj]:
        if object_type not in OBJECT_TYPES:
            raise OntologyError(f"Unknown object type '{object_type}'. Valid types: {sorted(OBJECT_TYPES)}")
        collection: list[Obj] = self._data[OBJECT_TYPES[object_type]]
        return collection

    def get(self, object_type: str, object_id: str) -> Obj:
        for obj in self._collection(object_type):
            if obj["id"] == object_id:
                return dict(obj)
        raise OntologyError(f"No {object_type} with id '{object_id}'")

    def search(self, object_type: str, query: str = "") -> list[Obj]:
        """Case-insensitive match of ``query`` against every field value."""
        q = query.strip().lower()
        return [dict(o) for o in self._collection(object_type) if not q or any(q in str(v).lower() for v in o.values())]

    def linked(self, object_type: str, object_id: str, target_type: str) -> list[Obj]:
        source = self.get(object_type, object_id)
        if (object_type, target_type) in LINKS:  # follow the foreign key outwards
            return [self.get(target_type, source[LINKS[(object_type, target_type)]])]
        if (target_type, object_type) in LINKS:  # find objects pointing back at this one
            fk = LINKS[(target_type, object_type)]
            return [dict(o) for o in self._collection(target_type) if o[fk] == object_id]
        raise OntologyError(f"No link between {object_type} and {target_type}")

    def leases_expiring(self, within_days: int) -> list[Obj]:
        horizon = self.as_of + dt.timedelta(days=within_days)
        return [
            dict(lease)
            for lease in self._collection("lease")
            if self.as_of <= dt.date.fromisoformat(lease["end_date"]) <= horizon
        ]

    # ---- actions (write operations; the agent must get human approval first) ----

    def create_work_order(self, unit_id: str, category: str, priority: str, description: str) -> Obj:
        self.get("unit", unit_id)
        if category not in WORK_ORDER_CATEGORIES:
            raise OntologyError(f"category must be one of {WORK_ORDER_CATEGORIES}")
        if priority not in PRIORITIES:
            raise OntologyError(f"priority must be one of {PRIORITIES}")
        if not description.strip():
            raise OntologyError("description is required")
        orders = self._collection("work_order")
        order = {
            "id": f"WO-{len(orders) + 1:04d}",
            "unit_id": unit_id,
            "category": category,
            "priority": priority,
            "status": "open",
            "description": description.strip(),
        }
        orders.append(order)
        self._audit("create_work_order", order["id"], order)
        return dict(order)

    def flag_lease_renewal(self, lease_id: str, note: str) -> Obj:
        lease = next((obj for obj in self._collection("lease") if obj["id"] == lease_id), None)
        if lease is None:
            raise OntologyError(f"No lease with id '{lease_id}'")
        if dt.date.fromisoformat(lease["end_date"]) < self.as_of:
            raise OntologyError(f"Lease {lease_id} has already ended; it cannot be flagged for renewal")
        lease["renewal_flagged"] = True
        lease["renewal_note"] = note.strip()
        self._audit("flag_lease_renewal", lease_id, {"note": note.strip()})
        return dict(lease)

    def _audit(self, action: str, object_id: str, payload: dict[str, Any]) -> None:
        self.audit_log.append(
            {"action": action, "object_id": object_id, "payload": payload, "at": dt.datetime.now(dt.UTC).isoformat()}
        )
