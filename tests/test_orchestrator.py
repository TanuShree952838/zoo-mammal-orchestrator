"""The orchestrator calls Agent 2 with Agent 1's list and stops on a bad contract."""

from __future__ import annotations

import logging

import pytest

from app.agents.base import AgentError
from app.agents.leg_agent import LegAgent
from app.agents.mammal_agent import MammalAgent
from app.orchestrator import Orchestrator
from app.schemas import (
    AGENT1_FAILURE_MESSAGE,
    AGENT2_FAILURE_MESSAGE,
    BAD_QUERY_MESSAGE,
    DEFAULT_QUERY,
    UNKNOWN_JUSTIFICATION,
    MammalSelection,
)

DEFAULT_FIVE = ["Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo"]
EXPECTED_MESSAGE = "\n".join(
    [
        "Mammals found in a zoo:",
        "1) Elephant",
        "2) Giraffe",
        "3) Lion",
        "4) Zebra",
        "5) Kangaroo",
        "",
        "Leg counts:",
        "- Elephant: 4",
        "- Giraffe: 4",
        "- Lion: 4",
        "- Zebra: 4",
        "- Kangaroo: 2",
    ]
)


class StaticAgent:
    """Returns a canned payload, or raises, and records each call."""

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list = []

    def run(self, task):
        self.calls.append(task)
        if self.error is not None:
            raise self.error
        return self.result


class RecordingLegAgent(LegAgent):
    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def run(self, task):
        self.seen.append(list(task))
        return super().run(task)


def test_default_query_returns_five_mammals_and_leg_counts():
    result = Orchestrator().run(DEFAULT_QUERY)

    assert result.status == "ok"
    assert result.mammals == DEFAULT_FIVE
    assert result.leg_counts == {
        "Elephant": 4,
        "Giraffe": 4,
        "Lion": 4,
        "Zebra": 4,
        "Kangaroo": 2,
    }
    assert result.message == EXPECTED_MESSAGE
    assert result.notes == []


def test_agent_2_is_called_once_with_agent_1_names():
    leg_agent = RecordingLegAgent()

    result = Orchestrator(leg_agent=leg_agent).run(DEFAULT_QUERY)

    assert leg_agent.seen == [DEFAULT_FIVE]
    assert result.mammals == DEFAULT_FIVE


def test_cleaned_names_are_what_agent_2_receives():
    raw = ["Elephant", "Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo", "Hippo"]
    leg_agent = RecordingLegAgent()

    result = Orchestrator(mammal_agent=MammalAgent(raw_output=raw), leg_agent=leg_agent).run(DEFAULT_QUERY)

    assert leg_agent.seen == [DEFAULT_FIVE]
    assert result.status == "ok"
    assert result.notes == [
        "Dropped duplicate: Elephant",
        "Trimmed extra mammal: Hippo",
    ]


def test_non_mammal_is_replaced_before_the_leg_handoff():
    raw = ["Elephant", "Giraffe", "Lion", "Zebra", "Crocodile"]
    leg_agent = RecordingLegAgent()

    result = Orchestrator(mammal_agent=MammalAgent(raw_output=raw), leg_agent=leg_agent).run(DEFAULT_QUERY)

    assert leg_agent.seen == [DEFAULT_FIVE]
    assert "Crocodile" not in result.mammals
    assert result.notes == [
        "Dropped non-mammal: Crocodile",
        "Completed the list from the catalog: Kangaroo",
    ]


@pytest.mark.parametrize("bad_output", [[], "not-a-list"])
def test_unusable_agent_1_output_skips_agent_2(bad_output):
    leg_agent = StaticAgent(result={})

    result = Orchestrator(
        mammal_agent=StaticAgent(result=bad_output),
        leg_agent=leg_agent,
    ).run(DEFAULT_QUERY)

    assert result.status == "error"
    assert result.message == AGENT1_FAILURE_MESSAGE
    assert result.mammals is None
    assert result.leg_counts is None
    assert leg_agent.calls == []


def test_agent_1_exception_is_a_safe_error():
    leg_agent = StaticAgent(result={})

    result = Orchestrator(
        mammal_agent=StaticAgent(error=AgentError("agent_1", "model exploded")),
        leg_agent=leg_agent,
    ).run(DEFAULT_QUERY)

    assert result.status == "error"
    assert result.message == AGENT1_FAILURE_MESSAGE
    assert "exploded" not in result.message
    assert leg_agent.calls == []


def test_missing_leg_key_is_partial_and_keeps_the_mammals():
    counts = {name: 4 for name in DEFAULT_FIVE if name != "Zebra"}
    leg_agent = StaticAgent(
        result={"leg_counts": counts, "justifications": {}, "status": "ok", "notes": []}
    )

    result = Orchestrator(
        mammal_agent=StaticAgent(result=_selection()),
        leg_agent=leg_agent,
    ).run(DEFAULT_QUERY)

    assert result.status == "partial"
    assert result.mammals == DEFAULT_FIVE
    assert result.leg_counts is None
    assert result.message.endswith(AGENT2_FAILURE_MESSAGE)
    assert "1) Elephant" in result.message


@pytest.mark.parametrize("bad_value", ["four", -1])
def test_illegal_leg_value_is_partial(bad_value):
    counts = {name: 4 for name in DEFAULT_FIVE}
    counts["Kangaroo"] = bad_value
    leg_agent = StaticAgent(
        result={"leg_counts": counts, "justifications": {}, "status": "ok", "notes": []}
    )

    result = Orchestrator(
        mammal_agent=StaticAgent(result=_selection()),
        leg_agent=leg_agent,
    ).run(DEFAULT_QUERY)

    assert result.status == "partial"
    assert result.leg_counts is None
    assert result.mammals == DEFAULT_FIVE


def test_agent_2_exception_keeps_the_mammal_list():
    result = Orchestrator(
        mammal_agent=StaticAgent(result=_selection()),
        leg_agent=StaticAgent(error=RuntimeError("counter offline")),
    ).run(DEFAULT_QUERY)

    assert result.status == "partial"
    assert result.mammals == DEFAULT_FIVE
    assert result.leg_counts is None
    assert "Elephant" in result.message
    assert "counter offline" not in result.message
    assert AGENT2_FAILURE_MESSAGE in result.message


def test_unknown_mammal_from_agent_1_is_counted_as_unknown():
    names = ["Elephant", "Giraffe", "Lion", "Zebra", "Okapi"]

    result = Orchestrator(
        mammal_agent=StaticAgent(result=_selection(names)),
        leg_agent=LegAgent(),
    ).run(DEFAULT_QUERY)

    assert result.status == "ok"
    assert result.leg_counts["Okapi"] == "unknown"
    assert result.leg_counts["Elephant"] == 4
    assert f"- Okapi: unknown ({UNKNOWN_JUSTIFICATION})" in result.message
    assert result.notes == ["Okapi: unknown"]


def test_query_without_then_calls_neither_agent():
    mammal_agent = StaticAgent(result=_selection())
    leg_agent = StaticAgent(result={})

    result = Orchestrator(mammal_agent=mammal_agent, leg_agent=leg_agent).run("Name 5 zoo mammals")

    assert result.status == "error"
    assert result.message == BAD_QUERY_MESSAGE
    assert mammal_agent.calls == []
    assert leg_agent.calls == []


def test_blank_side_of_then_is_rejected():
    result = Orchestrator().run("Then tell me how many legs those mammals have.")

    assert result.status == "error"
    assert result.message == BAD_QUERY_MESSAGE


def test_happy_path_logs_the_handoffs(caplog):
    caplog.set_level(logging.INFO)

    Orchestrator().run(DEFAULT_QUERY)

    messages = [record.message for record in caplog.records]
    assert "orchestrator received query" in messages
    assert any(message.startswith("orchestrator split task_a=") for message in messages)
    assert "handoff agent_1 start" in messages
    assert "handoff agent_1 done mammals=[Elephant, Giraffe, Lion, Zebra, Kangaroo]" in messages
    assert "handoff agent_2 start mammals=[Elephant, Giraffe, Lion, Zebra, Kangaroo]" in messages
    assert (
        "handoff agent_2 done leg_counts={Elephant: 4, Giraffe: 4, Lion: 4, Zebra: 4, Kangaroo: 2}"
        in messages
    )
    assert "orchestrator collated status=ok" in messages


def _selection(names: list[str] | None = None) -> MammalSelection:
    return MammalSelection(mammals=names or DEFAULT_FIVE, status="ok", notes=[])
