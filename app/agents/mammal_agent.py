"""Agent 1: choose five unique zoo mammals."""

from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentError
from app.schemas import MammalSelection

# Fixed order so the default answer and the top-up list stay deterministic.
CATALOG = [
    "Elephant",
    "Giraffe",
    "Lion",
    "Zebra",
    "Kangaroo",
    "Hippo",
    "Rhino",
    "Tiger",
    "Panda",
    "Gorilla",
]

_DEFAULT = object()
_BY_NAME = {name.casefold(): name for name in CATALOG}


class MammalAgent(Agent):
    """Turn a naming task into five catalog mammals."""

    name = "agent_1"

    def __init__(self, raw_output: Any = _DEFAULT) -> None:
        # Tests inject a messy model payload. The default is the first five.
        self._raw_output = raw_output

    def run(self, task: str) -> MammalSelection:
        if not isinstance(task, str) or not task.strip():
            raise AgentError(self.name, "naming task is empty")
        raw = CATALOG[:5] if self._raw_output is _DEFAULT else self._raw_output
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> MammalSelection:
        # Repair stays in this agent. The orchestrator only accepts a finished list of five.
        if not isinstance(raw, list):
            raise AgentError(self.name, "model output is not a list")

        notes: list[str] = []
        chosen: list[str] = []
        seen: set[str] = set()

        for entry in raw:
            canonical = _canonical(entry)
            if canonical is None:
                notes.append(f"Dropped non-mammal: {_label(entry)}")
                continue
            if canonical in seen:
                notes.append(f"Dropped duplicate: {canonical}")
                continue
            if len(chosen) == 5:
                notes.append(f"Trimmed extra mammal: {canonical}")
                continue
            seen.add(canonical)
            chosen.append(canonical)

        if len(chosen) < 5:
            added = _top_up(chosen, seen)
            if added:
                notes.append("Completed the list from the catalog: " + ", ".join(added))

        if len(chosen) != 5:
            raise AgentError(self.name, "catalog could not supply five mammals")

        status: str = "degraded" if notes else "ok"
        return MammalSelection(mammals=chosen, status=status, notes=notes)


def _canonical(entry: Any) -> str | None:
    if not isinstance(entry, str):
        return None
    return _BY_NAME.get(entry.strip().casefold())


def _label(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip() or "empty name"
    return str(entry)


def _top_up(chosen: list[str], seen: set[str]) -> list[str]:
    added: list[str] = []
    for name in CATALOG:
        if name in seen:
            continue
        chosen.append(name)
        seen.add(name)
        added.append(name)
        if len(chosen) == 5:
            break
    return added
