"""Pydantic contracts for the request, each agent, and the user envelope."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

DEFAULT_QUERY = (
    "Name 5 mammals that you find in the zoo. "
    "Then tell me how many legs those mammals have."
)

BAD_QUERY_MESSAGE = "Ask for five zoo mammals, then ask how many legs they have."
AGENT1_FAILURE_MESSAGE = "Could not name five zoo mammals. Please try again."
AGENT2_FAILURE_MESSAGE = "Leg counts could not be determined. Please try again."

UNKNOWN_LEG = "unknown"
UNKNOWN_JUSTIFICATION = "No locomotion leg count in the local reference table."


def _checked_leg(value: Any) -> Union[int, str]:
    # Legs are a non-negative int, or the word unknown. Nothing else is coerced.
    if value == UNKNOWN_LEG:
        return UNKNOWN_LEG
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("leg count must be an integer >= 0 or 'unknown'")
    return value


# Built at runtime, so this alias cannot use the 3.10 union operator.
LegValue = Annotated[Union[int, Literal["unknown"]], BeforeValidator(_checked_leg)]


class QueryRequest(BaseModel):
    """POST /query body."""

    model_config = ConfigDict(extra="forbid")

    query: str

    @field_validator("query")
    @classmethod
    def query_is_present(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class HealthResponse(BaseModel):
    status: Literal["ok"]


class MammalSelection(BaseModel):
    """Agent 1 contract: exactly five unique names."""

    model_config = ConfigDict(extra="forbid")

    mammals: list[str] = Field(min_length=5, max_length=5)
    status: Literal["ok", "degraded"]
    notes: list[str] = Field(default_factory=list)

    @field_validator("mammals")
    @classmethod
    def unique_non_empty_names(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for name in value:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("mammal names must be non-empty strings")
            cleaned.append(name.strip())
        folded = {name.casefold() for name in cleaned}
        if len(folded) != len(cleaned):
            raise ValueError("mammal names must be unique")
        return cleaned


class LegCountResult(BaseModel):
    """Agent 2 contract: one locomotion count per received mammal."""

    model_config = ConfigDict(extra="forbid")

    leg_counts: dict[str, LegValue]
    justifications: dict[str, str] = Field(default_factory=dict)
    status: Literal["ok", "degraded"]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def justifications_match_unknowns(self) -> Self:
        unknown = {name for name, legs in self.leg_counts.items() if legs == UNKNOWN_LEG}
        if set(self.justifications) != unknown:
            raise ValueError("justifications must explain each unknown count and nothing else")
        for name in unknown:
            if not self.justifications[name].strip():
                raise ValueError("justification must be non-empty")
        return self


class LegCoverage(BaseModel):
    """Orchestrator boundary: Agent 2 must cover Agent 1's names and no others."""

    model_config = ConfigDict(extra="forbid")

    mammals: list[str]
    leg_counts: dict[str, LegValue]
    justifications: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def covers_each_mammal(self) -> Self:
        if set(self.leg_counts) != set(self.mammals):
            raise ValueError("leg counts must match the mammal list")
        # Reuse Agent 2's justification rule on the filtered map.
        LegCountResult(
            leg_counts=self.leg_counts,
            justifications=self.justifications,
            status="ok",
            notes=[],
        )
        return self


class UserEnvelope(BaseModel):
    """What the CLI prints and what POST /query returns."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "partial", "error"]
    message: str
    mammals: Optional[list[str]] = None
    leg_counts: Optional[dict[str, LegValue]] = None
    notes: list[str] = Field(default_factory=list)
