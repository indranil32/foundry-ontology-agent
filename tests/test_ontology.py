import pytest

from ontology_agent.ontology import Ontology, OntologyError


def test_get_and_search(ontology: Ontology) -> None:
    assert ontology.get("unit", "U-001")["property_id"] == "P-001"
    assert [t["id"] for t in ontology.search("tenant", "cafe")] == ["T-003"]
    with pytest.raises(OntologyError, match="No unit"):
        ontology.get("unit", "U-999")
    with pytest.raises(OntologyError, match="Unknown object type"):
        ontology.search("building")


def test_links_both_directions(ontology: Ontology) -> None:
    lease = ontology.linked("unit", "U-002", "lease")[0]
    assert lease["unit_id"] == "U-002"
    tenant = ontology.linked("lease", lease["id"], "tenant")[0]
    assert tenant["id"] == lease["tenant_id"]
    with pytest.raises(OntologyError, match="No link"):
        ontology.linked("tenant", "T-001", "property")


def test_leases_expiring_window(ontology: Ontology) -> None:
    within_90 = ontology.leases_expiring(90)
    assert within_90 and all(lease["end_date"] >= "2026-11-01" for lease in within_90)
    assert len(ontology.leases_expiring(400)) >= len(within_90)


def test_create_work_order_validates_and_audits(ontology: Ontology) -> None:
    order = ontology.create_work_order("U-003", "plumbing", "high", "Leaking pipe under sink")
    assert order["status"] == "open" and order["unit_id"] == "U-003"
    assert ontology.audit_log[-1]["action"] == "create_work_order"
    with pytest.raises(OntologyError, match="category"):
        ontology.create_work_order("U-003", "roofing", "high", "x")
    with pytest.raises(OntologyError, match="No unit"):
        ontology.create_work_order("U-999", "plumbing", "high", "x")


def test_flag_renewal_rejects_ended_lease(ontology: Ontology) -> None:
    ended = [lease for lease in ontology.search("lease") if lease["end_date"] < "2026-11-01"]
    active = ontology.leases_expiring(400)[0]
    assert ontology.flag_lease_renewal(active["id"], "Tenant asked to renew")["renewal_flagged"] is True
    if ended:
        with pytest.raises(OntologyError, match="already ended"):
            ontology.flag_lease_renewal(ended[0]["id"], "late")
