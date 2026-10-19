"""Split the user request, hand off to each agent, and collate one reply."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.base import Agent, AgentError
from app.agents.leg_agent import LegAgent
from app.agents.mammal_agent import MammalAgent
from app.logging_config import get_logger
from app.schemas import (
    AGENT1_FAILURE_MESSAGE,
    AGENT2_FAILURE_MESSAGE,
    BAD_QUERY_MESSAGE,
    UNKNOWN_LEG,
    LegCountResult,
    LegCoverage,
    MammalSelection,
    UserEnvelope,
)

# One split. A later "then" stays inside the leg-count instruction.
_THEN = re.compile(r"\bthen\b", re.IGNORECASE)

logger = get_logger("app.orchestrator")


class Orchestrator:
    """Coordinate Agent 1 and Agent 2. It does not know the animal tables."""

    def __init__(
        self,
        mammal_agent: Agent | None = None,
        leg_agent: Agent | None = None,
    ) -> None:
        self._mammal_agent = mammal_agent or MammalAgent()
        self._leg_agent = leg_agent or LegAgent()

    def run(self, query: str) -> UserEnvelope:
        logger.info("orchestrator received query")
        try:
            task_a, task_b = _split_query(query)
        except ValueError:
            logger.info("orchestrator collated status=error")
            return _error(BAD_QUERY_MESSAGE, ["Query did not include both steps."])

        logger.info("orchestrator split task_a=%s task_b=%s", task_a, task_b)
        mammals = self._name_mammals(task_a)
        if isinstance(mammals, UserEnvelope):
            return mammals

        # task_b is the user's wording. The payload is Agent 1's list, not that sentence.
        return self._count_legs(mammals)

    def _name_mammals(self, task_a: str) -> MammalSelection | UserEnvelope:
        logger.info("handoff agent_1 start")
        try:
            raw = self._mammal_agent.run(task_a)
            selection = _coerce_mammals(raw)
        except AgentError:
            logger.info("handoff agent_1 failed")
            logger.info("orchestrator collated status=error")
            return _error(
                AGENT1_FAILURE_MESSAGE,
                ["Agent 1 could not complete the naming step."],
            )
        except Exception:
            logger.exception("handoff agent_1 failed")
            logger.info("orchestrator collated status=error")
            return _error(
                AGENT1_FAILURE_MESSAGE,
                ["Agent 1 could not complete the naming step."],
            )

        logger.info("handoff agent_1 done mammals=%s", _format_names(selection.mammals))
        return selection

    def _count_legs(self, selection: MammalSelection) -> UserEnvelope:
        logger.info("handoff agent_2 start mammals=%s", _format_names(selection.mammals))
        try:
            raw = self._leg_agent.run(selection.mammals)
            legs = _coerce_legs(raw, selection.mammals)
        except AgentError:
            logger.info("handoff agent_2 failed")
            return _partial(selection)
        except Exception:
            logger.exception("handoff agent_2 failed")
            return _partial(selection)

        logger.info("handoff agent_2 done leg_counts=%s", _format_counts(legs.leg_counts))
        envelope = UserEnvelope(
            status="ok",
            message=_success_message(selection.mammals, legs),
            mammals=list(selection.mammals),
            leg_counts=dict(legs.leg_counts),
            notes=[*selection.notes, *legs.notes],
        )
        logger.info("orchestrator collated status=ok")
        return envelope


def _split_query(query: str) -> tuple[str, str]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    parts = _THEN.split(query, maxsplit=1)
    if len(parts) != 2:
        raise ValueError("missing then")
    task_a, task_b = parts[0].strip(), parts[1].strip()
    if not task_a or not task_b:
        raise ValueError("blank step")
    return task_a, task_b


def _coerce_mammals(raw: Any) -> MammalSelection:
    try:
        if isinstance(raw, MammalSelection):
            payload: Any = raw.model_dump()
        elif isinstance(raw, list):
            payload = {"mammals": raw, "status": "ok", "notes": []}
        elif isinstance(raw, dict):
            payload = raw
        else:
            raise ValueError("not a mammal list")
        return MammalSelection.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise AgentError("agent_1", "invalid output") from exc


def _coerce_legs(raw: Any, mammals: list[str]) -> LegCountResult:
    try:
        if isinstance(raw, BaseModel):
            payload = raw.model_dump()
        elif isinstance(raw, dict):
            payload = raw
        else:
            raise ValueError("not a leg map")
        covered = LegCoverage.model_validate(
            {
                "mammals": mammals,
                "leg_counts": payload.get("leg_counts"),
                "justifications": payload.get("justifications", {}),
            }
        )
        return LegCountResult.model_validate(
            {
                "leg_counts": covered.leg_counts,
                "justifications": covered.justifications,
                "status": payload.get("status", "ok"),
                "notes": payload.get("notes", []),
            }
        )
    except (ValidationError, ValueError) as exc:
        raise AgentError("agent_2", "invalid output") from exc


def _partial(selection: MammalSelection) -> UserEnvelope:
    logger.info("orchestrator collated status=partial")
    lines = _mammal_lines(selection.mammals)
    lines.append("")
    lines.append(AGENT2_FAILURE_MESSAGE)
    return UserEnvelope(
        status="partial",
        message="\n".join(lines),
        mammals=list(selection.mammals),
        leg_counts=None,
        notes=[*selection.notes, "Agent 2 could not complete the leg-count step."],
    )


def _error(message: str, notes: list[str]) -> UserEnvelope:
    return UserEnvelope(status="error", message=message, mammals=None, leg_counts=None, notes=notes)


def _success_message(mammals: list[str], legs: LegCountResult) -> str:
    lines = _mammal_lines(mammals)
    lines.append("")
    lines.append("Leg counts:")
    for name in mammals:
        value = legs.leg_counts[name]
        if value == UNKNOWN_LEG:
            lines.append(f"- {name}: unknown ({legs.justifications[name]})")
        else:
            lines.append(f"- {name}: {value}")
    return "\n".join(lines)


def _mammal_lines(mammals: list[str]) -> list[str]:
    lines = ["Mammals found in a zoo:"]
    lines.extend(f"{index}) {name}" for index, name in enumerate(mammals, start=1))
    return lines


def _format_names(names: list[str]) -> str:
    return "[" + ", ".join(names) + "]"


def _format_counts(counts: dict[str, int | str]) -> str:
    inner = ", ".join(f"{name}: {value}" for name, value in counts.items())
    return "{" + inner + "}"
