# Scenario

A user asks:

> Name 5 mammals that you find in the zoo. Then tell me how many legs those mammals have.

Three components handle that request:

- The **orchestrator** splits the request, calls the sub-agents in order, validates each result, and returns one reply.
- **Agent 1** (mammal selection) names five zoo mammals.
- **Agent 2** (leg counting) takes Agent 1's list and reports how many legs each animal uses for locomotion.

The orchestrator sends only the naming half to Agent 1. It then sends Agent 1's structured list to Agent 2. It never skips Agent 1 or invents names for Agent 2. After both steps, it collates a single human-readable response.

## Clarifications

- Any common zoo mammals are valid (for example elephant, giraffe, lion, zebra, kangaroo).
- Legs means legs used for locomotion. A kangaroo is 2.
- If a leg count is uncertain, the value is `unknown` with a short justification. The system does not guess.
- The workflow runs locally. No external services are required.

## Functional requirements

- Three distinct components: Orchestrator, Agent 1, Agent 2.
- The final response includes (1) the list of mammals and (2) the leg count per mammal.
- The solution runs from the command line (`python main.py`) with a documented entrypoint.
- Outputs are structured so the workflow is deterministic enough to test.

Suggested output:

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

## Design expectations

- Readable, maintainable code with small functions and little duplication.
- Basic error handling for parsing, unexpected outputs, and empty or invalid lists.
- Orchestration stays in the orchestrator. Each sub-agent does one job.
- Lightweight logging of handoffs and intermediate results.
- A small automated test suite plus a one-command run.

A strong solution passes structured data between agents, validates at each boundary, and keeps the orchestrator thin:

- Agent 1 returns a structured list of names, not free-form prose.
- Agent 2 accepts that list and returns a mammal → legs map.
- The orchestrator checks those shapes with Pydantic and renders one message.
- Edge cases are explicit: duplicates, non-mammals, unknown legs.
- One-command run, a short README, and meaningful tests.

## Acceptance checks

- The naming step returns exactly five unique mammals.
- Each mammal has a leg count that is an integer, or `unknown` with a justification.
- The orchestrator uses Agent 1's output as Agent 2's input.
- The final response is consolidated and human readable.
- A local run finishes in under five seconds.

---

## How correctness, accuracy, metrics, and bias are handled

This section is the evaluation design for the workflow. It is not a live-model scorecard. The agents use local, deterministic tables so every check is repeatable.

### Correctness

Correctness means the pipeline did the right job in the right order, and the user never sees a stack trace.

| Check | How it is enforced |
| --- | --- |
| Two-step request | The query must contain `Then` with both sides non-empty. Otherwise neither agent is called. |
| Handoff order | Agent 2 is only called after Agent 1's list has passed Pydantic validation. Tests spy on Agent 2's input and assert it equals Agent 1's names. |
| Five unique names | Agent 1 must return a list of length 5 with unique, non-empty strings. Duplicates, blanks, and non-mammals are dropped inside Agent 1 and filled from its catalog. |
| Matching keys | Agent 2's map must cover exactly those five names. A missing key, extra key, negative number, or word like `"four"` is rejected. |
| Safe fallbacks | Agent 1 hard failure → error, Agent 2 is skipped. Agent 2 hard failure → partial: the mammal list is kept, leg counts are not invented. |
| Local run | No network. Default query and HTTP `/query` share `Orchestrator.run`. |

Logging records each handoff (`agent_1 done`, `agent_2 start`, `collated status=...`) so a failed step is visible without reading internals.

### Accuracy

Accuracy means the values themselves are right under the stated definition of legs.

- Locomotion is the only counting rule. Kangaroo is 2. The quadrupeds in the local table are 4.
- Agent 2 does not choose animals and does not guess. An animal missing from the table is `"unknown"` plus: `No locomotion leg count in the local reference table.`
- Names are matched case-insensitively against a documented catalog, then returned in canonical spelling (`Elephant`, not `elephant`).
- The default five mammals and their counts are fixed, so a successful run always produces the same message.

Accuracy is therefore a contract against a published table, not an opinion from a model.

### Metrics

These are the numbers used to decide whether a run is acceptable. They are checked by tests, not by a live scorer.

| Metric | Target | Where it is measured |
| --- | --- | --- |
| Mammal count | exactly 5 | Pydantic `min_length=5, max_length=5` and tests |
| Uniqueness | 5 distinct names | case-folded set size must equal list length |
| Leg value type | `int >= 0` or `"unknown"` | Pydantic validator; `"four"` and `-1` fail |
| Unknown justification | one non-empty reason per `"unknown"` | model validator on Agent 2 output |
| Handoff integrity | Agent 2 called once with Agent 1's list | orchestrator tests |
| Latency | under 5 seconds | local tables; suite currently finishes in well under 1 second |
| User-visible status | `ok` / `partial` / `error` | CLI exit code 0 for ok/partial, 1 for error; HTTP 200 / 400 / 502 |
| Safe messaging | no internal exception text in `message` | tests assert phrases like `exploded` never leak |

Regression coverage for those metrics lives in `tests/test_agents.py`, `tests/test_orchestrator.py`, and `tests/test_api.py`.

### Bias

Bias here means silently preferring some animals, inflating counts, or hiding uncertainty. The design keeps those choices explicit and small.

- **Documented default, not a hidden ranking.** The first five catalog names are the default answer. Later names (Hippo, Rhino, Tiger, Panda, Gorilla) are only used to top up a repaired list. Order is published so the default is inspectable.
- **No invented species or counts.** Agent 1 may only emit catalog mammals. Agent 2 may only emit table counts or `unknown`. That stops the system from "helpfully" guessing a number that looks confident but is wrong.
- **Unknown is preferred over a fake integer.** An Okapi-style name is reported as unknown with a justification, so the user can see the gap instead of receiving a made-up 4.
- **Repair is logged.** Dropped duplicates, dropped non-mammals, and catalog top-ups are written into `notes`. The user-facing message stays clean; the envelope still records what was changed.
- **Same pipeline for CLI and HTTP.** There is no alternate path that could answer a question with different animals or different counts.
- **Catalog is common zoo mammals.** The list is a small, typical set. It is not a claim about every mammal, every zoo, or every culture. Expanding it is a data change in Agent 1 and Agent 2, not a change to orchestration.

If a later local model is plugged in, it must still return the same Pydantic contracts. The orchestrator will keep rejecting malformed lists and guessed-looking values such as `"four"`.
