"""FastAPI adapter. Workflow logic stays in the orchestrator."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.logging_config import configure_logging
from app.orchestrator import Orchestrator
from app.schemas import (
    AGENT1_FAILURE_MESSAGE,
    BAD_QUERY_MESSAGE,
    HealthResponse,
    QueryRequest,
    UserEnvelope,
)


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    configure_logging()
    application = FastAPI(title="Zoo mammal orchestrator")
    application.state.orchestrator = orchestrator or Orchestrator()

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/query", response_model=UserEnvelope)
    def query(body: QueryRequest) -> JSONResponse:
        envelope = application.state.orchestrator.run(body.query)
        # Same body as the CLI. Only the HTTP status changes when a step fails.
        return JSONResponse(status_code=_status_code(envelope), content=envelope.model_dump())

    return application


def _status_code(envelope: UserEnvelope) -> int:
    if envelope.status in {"ok", "partial"}:
        return 200
    if envelope.message == BAD_QUERY_MESSAGE:
        return 400
    if envelope.message == AGENT1_FAILURE_MESSAGE:
        return 502
    return 502


app = create_app()
