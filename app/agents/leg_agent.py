"""Agent 2: count locomotion legs for a list of mammals."""

from __future__ import annotations

from app.agents.base import Agent, AgentError
from app.schemas import UNKNOWN_JUSTIFICATION, UNKNOWN_LEG, LegCountResult

# Legs used to walk or hop. Kangaroo is 2; the others here are quadrupeds.
LEG_TABLE = {
    "Elephant": 4,
    "Giraffe": 4,
    "Lion": 4,
    "Zebra": 4,
    "Hippo": 4,
    "Rhino": 4,
    "Tiger": 4,
    "Panda": 4,
    "Gorilla": 4,
    "Kangaroo": 2,
}

_BY_NAME = {name.casefold(): name for name in LEG_TABLE}


class LegAgent(Agent):
    """Map each incoming mammal to a leg count. Do not choose animals."""

    name = "agent_2"

    def run(self, task: list[str]) -> LegCountResult:
        if not isinstance(task, list) or not task:
            raise AgentError(self.name, "mammal list is empty")

        leg_counts: dict[str, int | str] = {}
        justifications: dict[str, str] = {}
        notes: list[str] = []

        for entry in task:
            if not isinstance(entry, str) or not entry.strip():
                raise AgentError(self.name, "mammal name is empty")
            name = entry.strip()
            known = _BY_NAME.get(name.casefold())
            if known is None:
                # Unknown is a value, not a guessed number.
                leg_counts[name] = UNKNOWN_LEG
                justifications[name] = UNKNOWN_JUSTIFICATION
                notes.append(f"{name}: unknown")
                continue
            leg_counts[name] = LEG_TABLE[known]

        status: str = "degraded" if notes else "ok"
        return LegCountResult(
            leg_counts=leg_counts,
            justifications=justifications,
            status=status,
            notes=notes,
        )
