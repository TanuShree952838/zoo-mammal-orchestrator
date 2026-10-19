# Zoo mammal orchestrator

A local orchestrator and two sub-agents. The user asks for five zoo mammals and then for their leg counts. The orchestrator sends the naming step to Agent 1, sends Agent 1's list to Agent 2, and returns one reply.

No network calls. Both agents use in-process tables so a run finishes immediately and stays deterministic.

The full problem statement, plus how correctness, accuracy, metrics, and bias are handled, is in [SCENARIO.md](SCENARIO.md).

## Run

Python 3.9 or newer. On macOS the commands are often `python3` / `python3.12` and `python3.12 -m pip` if `python` and `pip` are not on `PATH`.

```bash
python3.12 -m pip install -r requirements.txt
python3.12 main.py
```

An explicit question:

```bash
python3.12 main.py --query "Name 5 mammals that you find in the zoo. Then tell me how many legs those mammals have."
```

Exit code `0` means `ok` or `partial`. Exit code `1` means the request could not be answered.

HTTP:

```bash
python3.12 -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

- `GET /health`
- `POST /query` with `{"query": "..."}`

`200` is a full or partial answer. `400` means the question was not split into two steps. `422` means the body failed Pydantic validation. `502` means Agent 1 failed and Agent 2 was not called.

## Flow

1. The orchestrator splits the sentence on `Then`.
2. Agent 1 returns five unique zoo mammals (JSON list).
3. The orchestrator checks that list with Pydantic.
4. Agent 2 returns a mammal-to-legs map. Kangaroo is `2`. An animal it does not know is `"unknown"` plus a justification.
5. The orchestrator checks the map against Agent 1's names and renders one message.

Agent 1 repairs duplicates, non-mammals, and short lists from its own catalog. If Agent 1 still cannot return five names, the user gets: `Could not name five zoo mammals. Please try again.` If Agent 2 fails, the mammal list is kept and the message says leg counts could not be determined.

## Tests

```bash
python3.12 -m pytest -q
```

## Layout

```text
main.py                      # CLI adapter
app/api.py                   # FastAPI adapter
app/orchestrator.py          # split, handoff, validate, collate
app/agents/mammal_agent.py   # Agent 1
app/agents/leg_agent.py      # Agent 2
app/agents/base.py           # shared agent interface + AgentError
app/schemas.py               # Pydantic models
app/logging_config.py
```
