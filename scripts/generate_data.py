"""Generate the synthetic property ontology used by the agent.

All names, units and tenants are fictional. Run: python scripts/generate_data.py
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

SEED = 7
AS_OF = dt.date(2026, 11, 1)
OUT = Path(__file__).resolve().parents[1] / "src" / "ontology_agent" / "data" / "ontology.json"

PROPERTIES = [
    ("P-001", "Marina Heights", "residential"),
    ("P-002", "Creekside Offices", "commercial"),
    ("P-003", "Palm Retail Walk", "retail"),
]
TENANT_NAMES = [
    "Alder Analytics",
    "Birch & Co Legal",
    "Cedar Cafe",
    "Dune Fitness",
    "Ember Design Studio",
    "Falcon Logistics",
    "Gulf Pharmacy",
    "Harbor Dental",
    "Iris Florist",
    "Juniper Tech",
    "Kestrel Travel",
    "Lotus Bakery",
]
CATEGORIES = ["plumbing", "electrical", "hvac", "general"]


def build() -> dict[str, object]:
    rng = random.Random(SEED)
    properties = [{"id": pid, "name": name, "type": kind} for pid, name, kind in PROPERTIES]
    units, tenants, leases, work_orders = [], [], [], []
    for i, name in enumerate(TENANT_NAMES, start=1):
        prop = properties[(i - 1) % len(properties)]
        unit_id = f"U-{i:03d}"
        units.append(
            {
                "id": unit_id,
                "property_id": prop["id"],
                "floor": rng.randint(1, 20),
                "area_sqm": rng.choice([45, 60, 85, 120, 200]),
            }
        )
        tenant_id = f"T-{i:03d}"
        tenants.append({"id": tenant_id, "name": name, "contact_email": f"ops@{name.split()[0].lower()}.example"})
        end = AS_OF + dt.timedelta(days=rng.randint(-20, 400))
        leases.append(
            {
                "id": f"L-{i:03d}",
                "unit_id": unit_id,
                "tenant_id": tenant_id,
                "start_date": (end - dt.timedelta(days=365 * rng.choice([1, 2, 3]))).isoformat(),
                "end_date": end.isoformat(),
                "annual_rent_aed": rng.choice([60_000, 95_000, 140_000, 220_000]),
                "renewal_flagged": False,
            }
        )
    for n in range(1, 7):
        unit = rng.choice(units)
        work_orders.append(
            {
                "id": f"WO-{n:04d}",
                "unit_id": unit["id"],
                "category": rng.choice(CATEGORIES),
                "priority": rng.choice(["low", "medium", "high"]),
                "status": rng.choice(["open", "closed"]),
                "description": "Routine inspection follow-up",
            }
        )
    return {
        "as_of": AS_OF.isoformat(),
        "properties": properties,
        "units": units,
        "tenants": tenants,
        "leases": leases,
        "work_orders": work_orders,
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"Wrote {OUT}")
