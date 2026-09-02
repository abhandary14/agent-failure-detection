# PLAN.md — LLM Failure Detection System (Proof of Concept)

## Purpose

A portfolio project demonstrating production-grade LLM monitoring for a
tool-calling chatbot. The chatbot answers business questions over synthetic
transaction data using a locally-run open-weight model's tool-use API
(served via **Ollama**, kept entirely $0 cost — no cloud LLM provider is
used). The core value being demonstrated is not the chatbot — it's the
**flagging layer**: a deterministic, rule-based system that inspects a
completed tool-calling trace and decides whether the model's behavior was
trustworthy, plus a **failure injection harness** that proves the flagging
layer actually catches what it claims to catch.

**Cost note:** the project originally targeted Claude's tool-use API, but
that is pay-per-token with no ongoing free tier. To guarantee zero cost,
the LLM layer runs against a local model through Ollama instead. The
`Trace` object contract (question, tool calls, results, final response)
is provider-agnostic, so `flagging/`, `injection/`, and `eval/` are
unaffected by this swap — only `chatbot/agent.py`, `tools/schemas.py`,
and `config.py` differ from a Claude-backed version. A smaller local
model may organically produce more tool-calling mistakes than Claude
would; that's acceptable and even useful here; it gives the flagging
layer real, naturally-occurring failures to catch in addition to the
injected ones.

Priorities, in order: clarity > modularity > testability > feature
completeness. This is a demo a reviewer should be able to read start to
finish, not a system built for scale.

---

## Repository Layout

```
agent_failure_monitoring/
├── PLAN.md
├── README.md
├── config.py
├── main.py
├── run_validation.py
├── .env.example
├── requirements.txt
├── data/
│   ├── generate_synthetic_data.py
│   └── transactions.db              (generated, gitignored)
├── tools/
│   ├── __init__.py
│   ├── schemas.py                   # tool schema definitions (Ollama/OpenAI-style function schema)
│   ├── db.py                        # shared SQLite connection helper
│   ├── logging_utils.py             # shared JSONL structured logger
│   ├── get_revenue.py
│   ├── get_top_products.py
│   ├── get_user_transactions.py
│   ├── get_account_balance.py
│   ├── get_spending_by_category.py
│   └── get_product_details.py
├── chatbot/
│   ├── __init__.py
│   └── agent.py                     # tool-calling loop, trace builder
├── flagging/
│   ├── __init__.py
│   └── checks.py                    # 5 checks + verdict combiner
├── injection/
│   ├── __init__.py
│   └── inject.py                    # 4 injector families
├── eval/
│   ├── __init__.py
│   └── test_questions.py            # 30-50 labeled NL questions
└── logs/
    ├── tool_calls.jsonl             (generated)
    └── traces/                      (generated, one JSON per run)
```

Each of `tools/`, `chatbot/`, `flagging/`, `injection/` gets its own
`if __name__ == "__main__":` smoke test (or a small `_selftest.py` beside
it) so any layer can be exercised without running the full pipeline.

---

## Part 1 — Synthetic Data (`data/generate_synthetic_data.py`)

- Uses `Faker` to generate:
  - **users** (200+): `user_id` (e.g. `U0001`), `name`, `email`,
    `signup_date`, `account_status` (active/inactive/suspended, weighted).
  - **products** (20): `product_id` (e.g. `P001`), `name`, `category`
    (4-5 categories: Electronics, Home, Apparel, Books, Beauty), `price`,
    `launch_date`.
  - **transactions** (5000+): `transaction_id`, `user_id`, `product_id`,
    `amount` (derived from product price × quantity, with small noise),
    `quantity`, `transaction_date` (spread across one full year),
    `status` (completed/refunded/pending, weighted ~80/12/8).
- **Seasonality**: sample transaction dates from a weighted-by-month
  distribution so Nov/Dec get ~2-3x the baseline weight of other months.
- **Idempotency**: script drops and recreates all tables at the top of
  a single transaction (`DROP TABLE IF EXISTS` + `CREATE TABLE`), so
  re-running always yields a clean, fully-regenerated DB — no dupes,
  no manual cleanup step.
- Fixed `Faker.seed()` / `random.seed()` for reproducibility across runs
  (important later for the eval set's expected values to stay stable).
- Prints a small summary on completion (row counts, date range, per-month
  transaction counts) so Part 1 is self-verifying from the terminal.

---

## Part 2 — Tool Layer (`tools/`)

Shared pieces first:
- `tools/db.py` — single `get_connection()` helper (SQLite, row factory
  = dict-like rows), path pulled from `config.py`.
- `tools/logging_utils.py` — `log_tool_call(name, args, result, duration_ms)`
  appends one JSON line to `logs/tool_calls.jsonl`. Used by every tool.

Each tool module (`get_revenue.py`, etc.):
- A plain Python function, fully typed, with a docstring describing
  behavior, args, and return shape.
- All filtering/aggregation happens in the SQL (`WHERE`, `SUM`, `GROUP BY`,
  `ORDER BY ... LIMIT`), never by fetching everything and filtering in
  Python.
- Input validation up front: date strings parsed with `datetime.strptime`
  and rejected with a structured error if malformed; IDs checked for
  existence where cheap to check (e.g. a `SELECT 1` before aggregating,
  or just returning zero/empty for a valid-shaped-but-nonexistent ID vs.
  an error for a malformed ID — documented per tool).
- On any handled failure, returns `{"error": "<reason>"}` rather than
  raising — the chatbot layer needs a value it can hand back to Claude
  as a tool result, not an exception.
- Every call — success or error — goes through `log_tool_call`.

`tools/schemas.py` holds the six tool schemas (`name`, `description`,
`parameters` with JSON Schema types — Ollama's tool-calling format,
which mirrors OpenAI's function-calling schema) as a `TOOLS` list,
imported directly by `chatbot/agent.py`. One place to look to see
exactly what the model is offered.

**Deliverable checkpoint (per user's instruction):** after Part 1 + Part 2,
run the data generator, show row counts, then call each of the six tools
directly (no LLM involved) against known inputs and print results —
confirming the DB and tool layer are correct before wiring up the local
model.

---

## Part 3 — Chatbot Orchestration (`chatbot/agent.py`)

- `ask(question: str, session_user_id: str) -> Trace`
- System prompt built fresh per call, explicitly injecting:
  - **today's date** (from `datetime.now()`, formatted — never left for
    the model to infer)
  - **session_user_id**, with an explicit instruction that any
    user-scoped tool call must use this ID unless the question clearly
    names a different, authorized lookup (for this POC: always use
    session_user_id — no cross-user lookups are ever legitimate).
- Standard tool-use loop against the local Ollama server
  (`POST /api/chat` with `tools=...`): if the response includes
  `tool_calls`, execute the requested tool(s) locally via a
  name→function dispatch table, append tool results as messages, call
  again → repeat until a final text response with no further tool calls.
- Every LLM call wrapped by the Part 7 retry/backoff logic (connection
  errors / timeouts against the local server, not provider rate limits).
- Returns a `Trace` (plain dataclass or TypedDict) capturing: question,
  system_prompt, session_user_id, list of tool calls (name, args, result,
  timestamp), final response text, total latency, raw message history.
  This structured object — not the text — is the contract the flagging
  layer consumes, and is identical in shape regardless of which LLM
  backend produced it.
- Full trace also serialized to `logs/traces/<timestamp>_<id>.json` for
  later inspection.
- Model name, base URL, etc. all read from `config.py` — swapping local
  models (e.g. `llama3.1:8b` → `qwen2.5:7b`) means editing one file and
  running `ollama pull <model>`.

---

## Part 4 — Flagging Layer (`flagging/checks.py`)

Five independent, pure functions, each `(trace, ...) -> CheckResult`
where `CheckResult = {"passed": bool, "reason": str}`:

1. `tool_selection_check(trace, expected_tool)` — eval-mode only
   (requires ground truth); production mode substitutes a heuristic
   ("was any tool called when the question implies data lookup").
2. `argument_correctness_check(trace, expected_args)` — compares actual
   vs. expected args; dates compared after normalizing to `date` objects
   (tolerant of `2025-08-01` vs `Aug 1, 2025` style variance), other
   fields compared for exact/near match.
3. `access_scope_check(trace, session_user_id)` — scans every tool call
   for a `user_id` argument; any mismatch against `session_user_id` is
   an immediate hard fail, independent of every other check.
4. `numerical_faithfulness_check(trace)` — regexes numeric/currency
   tokens out of the final response text, regexes numeric values out of
   tool results, verifies every response number is traceable to a tool
   result within a small rounding tolerance.
5. `schema_validity_check(trace)` — every tool call's name exists in
   `tools.schemas.TOOLS` and every argument key is in that tool's
   declared `input_schema`.

`combine_verdict(trace, ...) -> Verdict`:
- `CLEAN` if all applicable checks pass.
- `FLAGGED` with the list of failed checks + reasons otherwise.
- Severity: `access_scope` failure → always `HIGH` (a user-boundary
  violation is a security/privacy incident class, not a quality
  nit — documented inline as a comment). `numerical_faithfulness` and
  `tool_selection` → `MEDIUM` (wrong facts or wrong data source
  materially mislead the user but don't leak another user's data).
  `argument_correctness` and `schema_validity` → `LOW`-`MEDIUM`
  depending on whether the wrong args still happened to be
  in-bounds/harmless vs. clearly wrong (documented in comments at the
  decision point).

No LLM-as-judge anywhere in this file — everything is regex, exact
comparison, or set membership.

---

## Part 5 — Failure Injection (`injection/inject.py`)

Takes a CLEAN trace (deep-copied, never mutates the original) and
returns `(corrupted_trace, ground_truth_record)`.

- `inject_wrong_tool(trace)` — swap the tool name for another valid tool
  name from the schema (keeping args as-is where plausible).
  `should_be_flagged_by = ["tool_selection_check", "schema_validity_check?"]`
  — documented precisely per injector, since a swapped tool with
  now-mismatched args may trip multiple checks; ground truth lists all
  checks the injection is *expected* to trip, not just the primary one.
- `inject_wrong_argument(trace, arg_type)` — `arg_type` in
  `{"date_shift", "wrong_id", "wrong_limit"}`; shifts a date range by N
  days, substitutes a different valid product/user ID, or changes a
  `limit` value. `should_be_flagged_by = ["argument_correctness_check"]`.
- `inject_access_violation(trace)` — replaces a `user_id` arg with a
  different real user's ID. `should_be_flagged_by = ["access_scope_check"]`.
- `inject_numerical_distortion(trace)` — parses a number out of the final
  response text and perturbs it (e.g. +$500) so it no longer matches any
  tool result. `should_be_flagged_by = ["numerical_faithfulness_check"]`.

Every injector returns the exact record shape specified by the user:
`{"injection_type": ..., "detail": ..., "should_be_flagged_by": [...]}`.

---

## Part 6 — Validation Harness (`eval/` + `run_validation.py`)

- `eval/test_questions.py`: 30-50 hand-written questions, hand-labeled,
  covering all six tools (roughly balanced), each entry:
  `{"question": ..., "expected_tool": ..., "expected_args": {...}}`.
- `run_validation.py`:
  1. Run every question through `chatbot.agent.ask(...)`.
  2. Run flagging on the baseline trace; expect `CLEAN`. If not CLEAN,
     print a loud `BASELINE FAILURE` warning (this is a real chatbot bug,
     not a flagging false positive) and exclude that case from injection
     scoring but report it separately.
  3. For each CLEAN baseline, run every *applicable* injector (e.g. no
     access-violation injection on a tool with no `user_id` arg) to
     produce corrupted traces + ground truth.
  4. Run flagging on every corrupted trace.
  5. Score actual flagged-checks vs. `should_be_flagged_by` ground truth.
  6. Compute precision/recall/F1 overall and per-check-type.
  7. Print a full results table and also write it to CSV
     (`eval/results.csv`) — one row per (question, injection_type) with
     expected/actual/correct.

---

## Part 7 — Retry / Backoff Handling

Originally scoped as "rate limit handling" for a paid, rate-limited API.
Running against a local Ollama server instead removes provider rate
limits (429s) entirely, but the same wrapper is still worth keeping for
robustness against local failure modes: the Ollama server not yet warmed
up, a model still loading into memory, or a dropped local connection.

- A small `chatbot/retry.py`-style wrapper (or inline in `agent.py`)
  around the local LLM call: catches connection errors / timeouts /
  5xx from the local Ollama server, exponential backoff (e.g. 1s, 2s,
  4s, 8s, 16s), max 5 retries, logs each retry hit to the structured
  log so failure frequency is visible after a run.
- `config.py` exposes `INTER_CALL_DELAY_SECONDS` (default near-zero,
  since there's no external rate limit to respect) applied between LLM
  calls, tunable without touching code — useful mainly to avoid
  saturating local CPU/GPU during the validation suite's many
  back-to-back calls.

---

## config.py contents

- `OLLAMA_BASE_URL` (default `http://localhost:11434`) and `OLLAMA_MODEL`
  (default `llama3.1:8b` — Ollama's default pull for this tag is a
  4-bit quantized (Q4_K_M) 8B model, ~4.7GB download), overridable via
  env if set — no API key required since Ollama runs unauthenticated
  on localhost by default. Chosen over the smaller `llama3.2:3b` for
  meaningfully more reliable native tool-calling while remaining free
  and runnable on modest hardware. Swapping models means editing this
  one value and running `ollama pull <model>`.
- `MAX_TOKENS`, `MAX_TOOL_ITERATIONS`.
- `DB_PATH`, `LOG_DIR`.
- `INTER_CALL_DELAY_SECONDS`, `MAX_RETRIES`, retry backoff base.
- Flagging tolerances (date fuzz, numeric rounding tolerance).

`python-dotenv` / `.env` is kept in the project (harmless, and future-
proofs against re-adding a cloud provider later) but nothing required
for the default local setup needs to go in it.

---

## Build Order (confirmed with user)

1. **Part 1 + Part 2** — synthetic data + tool layer. Stop here, show
   generated data summary and direct tool-call outputs, get confirmation
   before proceeding.
2. Part 3 — chatbot orchestration.
3. Part 4 — flagging layer.
4. Part 5 — injection.
5. Part 6 — eval set + validation harness.
6. Part 7 — folded in during Part 3 (retry logic lives in the same call
   path) but verified/tuned once real API calls are happening in Part 6.
7. README.md, including the documented "Next Steps" section (prompt-level
   injection, Phoenix integration) as **documentation only** — no
   scaffolding, stubs, or new dependencies for either.

## Out of scope for this pass

- LLM-as-judge anywhere in flagging (hard requirement, not a suggestion).
- Prompt-level/organic failure injection (documented as future work only).
- Arize Phoenix / OpenTelemetry instrumentation (documented as future
  work only).
- Any production concerns beyond what's needed for a working, readable
  demo: no auth system, no multi-tenant DB, no deployment tooling.
