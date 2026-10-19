# MVP Artefact — Zoo Mammal Orchestrator

Status: draft for review. No application code yet.

This document is the flow you can verify before implementation. It describes a local FastAPI service plus a one-command CLI. Three components do one job each. Data between them is structured. If a step fails, the user gets a clear response instead of a stack trace.

## 1. What the user gets

Input (fixed scenario):

> Name 5 mammals that you find in the zoo. Then tell me how many legs those mammals have.

Success output (human-readable text, always this shape):

```text
Mammals found in a zoo:
1) Elephant
2) Giraffe
3) Lion
4) Zebra
5) Kangaroo

Leg counts:
- Elephant: 4
- Giraffe: 4
- Lion: 4
- Zebra: 4
- Kangaroo: 2
```

Rules baked into that output:

- Exactly five unique mammals.
- Legs mean legs used for locomotion. Kangaroo is 2.
- A missing or uncertain count is the string `unknown`, with a one-line justification kept beside it.
- The default five above are deterministic so tests do not depend on a live model.

## 2. Components

| Component | Owns | Does not own |
| --- | --- | --- |
| Orchestrator | Split the user sentence, call Agent 1, validate that result, call Agent 2 with that result, validate that result, collate one reply, map failures to a user message | Which mammals exist, how many legs they have |
| Agent 1 — mammal selection | Turn "name 5 zoo mammals" into a structured list of five unique zoo mammals | Leg counts, final prose |
| Agent 2 — leg counting | Turn that list into a mammal → legs map | Choosing mammals, final prose |

Both agents sit behind one interface: `run(task) -> structured result`. The default implementation is local and deterministic (an in-process reference table). The interface is where a later local model would plug in. Nothing in this MVP calls a network.

```text
CLI  ──┐
       ├── Orchestrator.run(query) ──► Agent 1 ── list ──► Agent 2 ── map ──► one message
HTTP ──┘
```

FastAPI and the CLI are thin adapters. They do not contain workflow logic.

## 3. Happy-path flow

```text
User
  │  query
  ▼
Orchestrator
  │  1. Split on "Then" into task A and task B
  │  2. Reject the query if either part is missing (no agent calls)
  │
  │  task A: "Name 5 mammals that you find in the zoo."
  ▼
Agent 1
  │  returns JSON list of 5 unique mammal names
  ▼
Orchestrator
  │  3. Validate shape: list, length 5, unique, non-empty strings
  │  4. On failure, stop. Do not call Agent 2.
  │
  │  task B payload = Agent 1 list (not the raw sentence)
  ▼
Agent 2
  │  returns JSON object mammal → legs
  ▼
Orchestrator
  │  5. Validate: same five keys, each value an int ≥ 0 or "unknown"
  │  6. Render the consolidated message
  ▼
User
```

Handoff log lines (INFO), in order, on the happy path:

1. `orchestrator received query`
2. `orchestrator split task_a=... task_b=...`
3. `handoff agent_1 start`
4. `handoff agent_1 done mammals=[Elephant, Giraffe, Lion, Zebra, Kangaroo]`
5. `handoff agent_2 start mammals=[...]`
6. `handoff agent_2 done leg_counts={...}`
7. `orchestrator collated status=ok`

Agent 2 is never called with a hand-written list. Its only input is the validated Agent 1 list.

## 4. Contracts

### 4.1 Agent 1 result

```json
{
  "mammals": ["Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo"],
  "status": "ok",
  "notes": []
}
```

`status` is `ok` or `degraded`. `notes` explains any cleanup Agent 1 applied (dropped a duplicate, dropped a non-mammal, topped up from its catalog).

### 4.2 Agent 2 result

```json
{
  "leg_counts": {
    "Elephant": 4,
    "Giraffe": 4,
    "Lion": 4,
    "Zebra": 4,
    "Kangaroo": 2
  },
  "justifications": {},
  "status": "ok",
  "notes": []
}
```

When a count is uncertain:

```json
{
  "leg_counts": { "Okapi": "unknown" },
  "justifications": {
    "Okapi": "No locomotion leg count in the local reference table."
  },
  "status": "degraded",
  "notes": ["Okapi: unknown"]
}
```

`justifications` is required for every `"unknown"` and empty otherwise.

### 4.3 User envelope (CLI and HTTP share this)

```json
{
  "status": "ok",
  "message": "Mammals found in a zoo:\n1) Elephant\n...",
  "mammals": ["Elephant", "Giraffe", "Lion", "Zebra", "Kangaroo"],
  "leg_counts": { "Elephant": 4, "Giraffe": 4, "Lion": 4, "Zebra": 4, "Kangaroo": 2 },
  "notes": []
}
```

`status` is one of `ok`, `partial`, `error`.

- `ok` — five mammals and a leg value for each.
- `partial` — Agent 1 succeeded, Agent 2 did not. `mammals` is filled, `leg_counts` is `null`, `message` still lists the mammals and then states that leg counts could not be determined.
- `error` — nothing useful to return (bad query, or Agent 1 failed). `mammals` and `leg_counts` are `null`. `message` is one plain sentence.

`notes` is for the operator and the tests. `message` is what a person reads. Internal exception text never appears in `message`.

## 5. Who fixes what

Cleanup that still produces five mammals stays inside the agent that owns the data. The orchestrator only checks the contract and decides whether to continue.

| Situation | Where it is handled | User-visible result |
| --- | --- | --- |
| Duplicate names from Agent 1's model | Agent 1 drops duplicates, tops up from its catalog to five | `ok` or `degraded` inside Agent 1; final `status=ok`; note lists dropped names |
| More than five names | Agent 1 keeps the first five unique valid mammals | `status=ok`; note lists trimmed names |
| Fewer than five valid names | Agent 1 tops up from its catalog, preserving order of valid names | `status=ok`; note says the list was completed from the catalog |
| Non-mammal in the list (`Crocodile`, `""`, numbers) | Agent 1 drops it, then tops up if needed | `status=ok`; note names what was dropped |
| Animal Agent 2 does not know | Agent 2 sets that entry to `"unknown"` plus a justification | `status=ok`; line reads `- Okapi: unknown (No locomotion leg count...)` |
| Agent 1 raises, times out, or returns a shape that cannot be repaired (not a list, all entries empty after cleanup, catalog itself unavailable) | Orchestrator catches `AgentError`, does not call Agent 2 | `status=error`, HTTP 502, message: `Could not name five zoo mammals. Please try again.` |
| Agent 2 raises, times out, or returns a shape that cannot be repaired | Orchestrator keeps Agent 1's list | `status=partial`, HTTP 200, mammals printed, then `Leg counts could not be determined. Please try again.` |
| Query has no "Then", or one side is blank | Orchestrator, before any agent call | `status=error`, HTTP 400, message: `Ask for five zoo mammals, then ask how many legs they have.` |
| Empty body / missing `query` | API adapter | HTTP 422, validation error from FastAPI |

Agent 1's catalog (selection order is fixed):

`Elephant, Giraffe, Lion, Zebra, Kangaroo, Hippo, Rhino, Tiger, Panda, Gorilla`

Agent 2's table (locomotion legs):

| Mammal | Legs |
| --- | --- |
| Elephant, Giraffe, Lion, Zebra, Hippo, Rhino, Tiger | 4 |
| Panda, Gorilla | 4 |
| Kangaroo | 2 |

Anything else Agent 2 is asked about becomes `"unknown"` with the justification in section 4.2. Agent 2 does not guess.

Degraded-but-repaired agent results are still passed downstream. A hard `AgentError` stops the pipeline as in the table. The user always receives the envelope in section 4.3.

## 6. Runtime surface

### CLI

```bash
python main.py
python main.py --query "Name 5 mammals that you find in the zoo. Then tell me how many legs those mammals have."
```

No query flag runs the scenario sentence above. Prints `message` to stdout. Exit code `0` for `ok` and `partial`, `1` for `error`.

### HTTP

| Method | Path | Body | Success |
| --- | --- | --- | --- |
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/query` | `{"query":"..."}` | envelope in section 4.3 |

```bash
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Status codes: `200` ok or partial, `400` bad query, `422` missing field, `502` Agent 1 hard failure.

## 7. Layout to build after sign-off

```text
main.py                      # CLI adapter
app/api.py                   # FastAPI adapter
app/orchestrator.py          # split, handoff, validate, collate
app/agents/mammal_agent.py   # Agent 1
app/agents/leg_agent.py      # Agent 2
app/agents/base.py           # shared agent interface + AgentError
app/schemas.py               # request/response models
app/logging_config.py
tests/test_agents.py
tests/test_orchestrator.py
tests/test_api.py
README.md
```

Reference data lives inside the agent that uses it. There is no shared catalog module, so the orchestrator cannot answer either question on its own.

## 8. Tests that lock the flow

Unit tests call the orchestrator with a fake agent that returns a canned payload or raises `AgentError`. They do not start a server. API tests use FastAPI's test client. Target runtime for the suite is well under 5 seconds.

| # | Check | Expect |
| --- | --- | --- |
| 1 | Default query | Exactly the five mammals in section 1, legs 4/4/4/4/2, `status=ok` |
| 2 | Spy on call order | Agent 2 is invoked once, with Agent 1's list and no other names |
| 3 | Agent 1 returns duplicates and a sixth name | Five unique names reach Agent 2; note records the cleanup |
| 4 | Agent 1 returns `Crocodile` plus four mammals | Crocodile dropped, fifth mammal filled from the catalog |
| 5 | Agent 1 returns `[]` or `"not-a-list"` | `status=error`, Agent 2 not called |
| 6 | Agent 1 raises | `status=error`, safe message, Agent 2 not called |
| 7 | Agent 2 returns a missing key | `status=partial`, mammals preserved, `leg_counts=null` |
| 8 | Agent 2 returns `"four"` or `-1` | `status=partial` (value is not an int ≥ 0 and not `"unknown"`) |
| 9 | Agent 2 raises after a good Agent 1 result | `status=partial`, mammal list still in `message` |
| 10 | Agent 2 is given `Okapi` | that entry is `"unknown"` and `justifications` explains why |
| 11 | Query without `Then` | `status=error`, neither agent called |
| 12 | `POST /query` happy path | HTTP 200 and the same message as the CLI |
| 13 | `POST /query` when Agent 1 raises | HTTP 502 and the safe sentence from section 5 |
| 14 | `GET /health` | HTTP 200 |

Manual check after implementation:

```bash
python main.py
pytest -q
```

## 9. Decisions to confirm

1. Default mammals are Elephant, Giraffe, Lion, Zebra, Kangaroo, in that order, every run.
2. Kangaroo is 2. Unknown species are the string `unknown` plus a justification, not a guessed integer.
3. Repairable junk (duplicates, non-mammals, short lists) is fixed inside Agent 1 and the workflow continues.
4. Agent 1 hard failure → `error`, Agent 2 is skipped.
5. Agent 2 hard failure → `partial`: the mammal list is returned, leg counts are not invented.
6. Both the CLI and `POST /query` call the same `Orchestrator.run`.
7. No network calls. Models, if added later, must be local and must still return the contracts in section 4.

Reply with changes to any row in section 5 or any decision in section 9. Implementation starts after this artefact is confirmed.
