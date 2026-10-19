"""Shared agent interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentError(Exception):
    """Raised when an agent result cannot be repaired."""

    def __init__(self, agent_name: str, reason: str) -> None:
        self.agent_name = agent_name
        # reason is for logs. The orchestrator replaces it with a fixed sentence.
        self.reason = reason
        super().__init__(f"{agent_name} failed: {reason}")


class Agent(ABC):
    """One job. Return a pydantic model, or raise AgentError."""

    name: str

    @abstractmethod
    def run(self, task: Any) -> Any:
        """Execute the task and return structured data."""
