"""Agent 1 repairs its own list. Agent 2 only counts legs."""

from __future__ import annotations

import pytest

from app.agents.base import AgentError
from app.agents.leg_agent import LegAgent
from app.agents.mammal_agent import MammalAgent
from app.schemas import UNKNOWN_JUSTIFICATION

DEFAULT_FIVE = ["Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo"]


def test_default_selection_is_the_five_zoo_mammals():
    result = MammalAgent().run("Name 5 mammals that you find in the zoo.")

    assert result.mammals == DEFAULT_FIVE
    assert result.status == "ok"
    assert result.notes == []


def test_duplicates_and_a_sixth_name_collapse_to_five():
    raw = ["Elephant", "Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo", "Hippo"]

    result = MammalAgent(raw_output=raw).run("Name 5 mammals.")

    assert result.mammals == DEFAULT_FIVE
    assert result.status == "degraded"
    assert result.notes == [
        "Dropped duplicate: Elephant",
        "Trimmed extra mammal: Hippo",
    ]


def test_non_mammal_is_dropped_and_the_list_is_completed():
    raw = ["Elephant", "Giraffe", "Lion", "Zebra", "Crocodile"]

    result = MammalAgent(raw_output=raw).run("Name 5 mammals.")

    assert result.mammals == DEFAULT_FIVE
    assert result.notes == [
        "Dropped non-mammal: Crocodile",
        "Completed the list from the catalog: Kangaroo",
    ]


def test_empty_model_list_is_filled_from_the_catalog():
    result = MammalAgent(raw_output=[]).run("Name 5 mammals.")

    assert result.mammals == DEFAULT_FIVE
    assert result.notes == [
        "Completed the list from the catalog: Elephant, Giraffe, Lion, Zebra, Kangaroo",
    ]


def test_non_list_model_output_raises():
    with pytest.raises(AgentError):
        MammalAgent(raw_output="not-a-list").run("Name 5 mammals.")


def test_numbers_and_blanks_are_dropped():
    raw = ["", 4, "Lion", "Zebra", "Kangaroo", "Hippo", "Rhino"]

    result = MammalAgent(raw_output=raw).run("Name 5 mammals.")

    assert result.mammals == ["Lion", "Zebra", "Kangaroo", "Hippo", "Rhino"]
    assert "Dropped non-mammal: empty name" in result.notes
    assert "Dropped non-mammal: 4" in result.notes


def test_okapi_leg_count_is_unknown_with_a_justification():
    result = LegAgent().run(["Okapi"])

    assert result.leg_counts == {"Okapi": "unknown"}
    assert result.justifications == {"Okapi": UNKNOWN_JUSTIFICATION}
    assert result.status == "degraded"
    assert result.notes == ["Okapi: unknown"]


def test_known_leg_counts_use_locomotion():
    result = LegAgent().run(DEFAULT_FIVE)

    assert result.leg_counts == {
        "Elephant": 4,
        "Giraffe": 4,
        "Lion": 4,
        "Zebra": 4,
        "Kangaroo": 2,
    }
    assert result.justifications == {}
    assert result.status == "ok"


def test_leg_agent_rejects_an_empty_list():
    with pytest.raises(AgentError):
        LegAgent().run([])
