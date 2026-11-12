import pytest

from ontology_agent.prompts import available_versions, load_prompt


def test_latest_version_is_default() -> None:
    assert available_versions("triage") == ["v1", "v2"]
    assert load_prompt("triage").version == "v2"


def test_pin_version_explicitly_and_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_prompt("triage", "v1").version == "v1"
    monkeypatch.setenv("PROMPT_VERSION_TRIAGE", "v1")
    assert load_prompt("triage").version == "v1"


def test_unknown_version_fails_loudly() -> None:
    with pytest.raises(ValueError, match="not found"):
        load_prompt("triage", "v9")
