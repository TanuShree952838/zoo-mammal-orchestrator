"""HTTP status codes and the CLI share the orchestrator envelope."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.base import AgentError
from app.api import create_app
from app.orchestrator import Orchestrator
from app.schemas import AGENT1_FAILURE_MESSAGE, DEFAULT_QUERY

ROOT = Path(__file__).resolve().parents[1]


class BoomAgent:
    def run(self, task):
        raise AgentError("agent_1", "model exploded")


def test_health():
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_query_matches_the_cli_message():
    completed = subprocess.run(
        [sys.executable, "main.py"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    response = TestClient(create_app()).post("/query", json={"query": DEFAULT_QUERY})

    assert completed.returncode == 0
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == completed.stdout.rstrip("\n")
    assert body["mammals"] == ["Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo"]
    assert body["leg_counts"]["Kangaroo"] == 2


def test_agent_1_failure_is_502_with_the_safe_sentence():
    client = TestClient(create_app(Orchestrator(mammal_agent=BoomAgent())))
    response = client.post("/query", json={"query": DEFAULT_QUERY})

    assert response.status_code == 502
    body = response.json()
    assert body["message"] == AGENT1_FAILURE_MESSAGE
    assert "exploded" not in body["message"]
    assert body["mammals"] is None


def test_query_without_then_is_400():
    response = TestClient(create_app()).post("/query", json={"query": "Name 5 mammals"})

    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_missing_query_field_is_422():
    response = TestClient(create_app()).post("/query", json={})

    assert response.status_code == 422


def test_cli_error_exits_nonzero():
    completed = subprocess.run(
        [sys.executable, "main.py", "--query", "just mammals"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert completed.returncode == 1
    assert "Ask for five zoo mammals" in completed.stdout
