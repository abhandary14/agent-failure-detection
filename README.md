# LLM Failure Detection System (Proof of Concept)

A portfolio project demonstrating production-grade monitoring for a
tool-calling LLM chatbot. The chatbot answers business questions over
synthetic transaction data using a locally-run open-weight model (Llama
3.1 8B, 4-bit quantized, served via [Ollama](https://ollama.com) --
entirely free, no cloud API key). The core value isn't the chatbot itself
-- it's the **flagging layer**, a deterministic rule-based system that
inspects a completed tool-calling trace and decides whether the model's
behavior was trustworthy, plus a **failure injection harness** that
proves the flagging layer actually catches what it claims to catch.

See [PLAN.md](PLAN.md) for the original design plan.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Failure Taxonomy](#failure-taxonomy)
- [Setup](#setup)
- [Running the Synthetic Data Generator](#running-the-synthetic-data-generator)
- [Running a Single Question](#running-a-single-question)
- [Running the Web UI](#running-the-web-ui)
- [Running the Full Validation Suite](#running-the-full-validation-suite)
- [Testing Each Layer in Isolation](#testing-each-layer-in-isolation)
- [Screenshots](#screenshots)
- [Next Steps](#next-steps)

---

## Project Structure

```
├── config.py                  # model selection, paths, thresholds -- single source of truth
├── main.py                    # entry point: run one question through the full pipeline
├── run_validation.py          # entry point: run the full validation suite, print metrics
├── data/
│   └── generate_synthetic_data.py   # builds data/transactions.db (idempotent)
├── tools/                     # 6 tool functions + Ollama-format schemas
│   ├── schemas.py             # tool_use-style schemas + dispatch table
│   ├── db.py, logging_utils.py, validation.py   # shared helpers
│   ├── get_revenue.py
│   ├── get_top_products.py
│   ├── get_user_transactions.py
│   ├── get_account_balance.py
│   ├── get_spending_by_category.py
│   └── get_product_details.py
├── chatbot/
│   ├── agent.py                # tool-calling loop, Trace object, system prompt
│   └── retry.py                 # exponential backoff for local Ollama calls
├── flagging/
│   └── checks.py               # 5 deterministic checks + verdict combiner
├── injection/
│   └── inject.py               # 4 injector families + applicable_injectors()
├── eval/
│   └── test_questions.py       # 36 hand-labeled NL questions
├── ui/
│   ├── server.py                # Flask app: /ask and /inject endpoints
│   └── static/index.html        # chat UI with live flagging + injection buttons
└── logs/
    ├── tool_calls.jsonl         # structured log of every tool call
    └── traces/                  # one JSON file per chatbot run
```

Every layer (`tools/`, `flagging/`, `injection/`) has its own
`_selftest.py` so it can be exercised independently of the LLM and of
each other -- see [Testing Each Layer in Isolation](#testing-each-layer-in-isolation).

---

## Failure Taxonomy

The flagging layer checks five independent failure categories. Each maps
to a real way a tool-calling LLM can go wrong in production, and each is
checked deterministically -- no LLM-as-judge anywhere in this system.

| Check | What it catches | Why it matters | Severity |
|---|---|---|---|
| **Tool selection** | Model called the wrong tool (or none) for the question | Wrong data source -> answer is about the wrong thing entirely | MEDIUM |
| **Argument correctness** | Tool was called with wrong/corrupted arguments (bad date range, wrong ID, wrong limit) | Right tool, wrong query -> plausible-looking but incorrect answer | MEDIUM |
| **Access scope** | A user-scoped tool call used a `user_id` other than the session user | **Hard fail, always.** This is a privacy/security boundary violation -- one user's financial data returned under another user's session -- not a quality defect. Never downgraded regardless of what else passed. | **HIGH** |
| **Numerical faithfulness** | A number in the final response doesn't trace back to any tool result (or a derived sum/count over one) | The model misstated a fetched figure -- the classic "confident but wrong" LLM failure | MEDIUM |
| **Schema validity** | A tool call referenced an undeclared tool or used undeclared/missing parameters | Model hallucinated a tool or a parameter that doesn't exist -- a hard functional break | MEDIUM |

`access_scope` is the only category that gets HIGH severity unconditionally
-- see the comment above `_SEVERITY_BY_CHECK` in `flagging/checks.py` for
the full reasoning.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

Install [Ollama](https://ollama.com/download) separately, then pull the model:

```bash
ollama pull llama3.1:8b
```

Ollama typically runs as a background service after install -- no need to
run `ollama serve` manually unless you see a "connection refused" error.

No API key or `.env` configuration is required for the default local
setup (`python-dotenv` is still a dependency in case a cloud provider is
added later, but nothing reads from `.env` by default).

---

## Running the Synthetic Data Generator

```bash
python data/generate_synthetic_data.py
```

Builds `data/transactions.db`: 200 users, 20 products across 5 categories,
5000 transactions over the last year with a realistic Nov/Dec seasonal
bump. Idempotent -- re-running always resets and regenerates cleanly.
Prints a summary with row counts and a per-month bar chart.

### 📸 Screenshot: Data generation output
Run the command above and capture the terminal output showing the summary
block (row counts, date range, and the per-month bar chart with Nov/Dec
visibly taller than other months).

---

## Running a Single Question

```bash
python main.py "What was our revenue on P001 in the last year?" U0001
```

Second argument is the `session_user_id` -- the "logged-in user" the
system prompt scopes user-specific tool calls to. Prints the tool call(s)
made, their results, and the final response. The full trace is also saved
to `logs/traces/`.

### 📸 Screenshot: Single question terminal output
Run the command above (or a similar revenue/product question) and capture
the terminal showing the tool call, its arguments/result, and the final
natural-language response.

---

## Running the Web UI

```bash
python ui/server.py
```

Then open **http://localhost:5000**. A minimal chat interface where every
response shows a live flagging verdict badge (CLEAN / FLAGGED + severity)
plus a collapsible detail panel with the exact tool call(s) and result(s).

The UI runs flagging in **production mode** -- no `expected_tool` /
`expected_args` ground truth exists for a live question, so only
`access_scope`, `numerical_faithfulness`, and `schema_validity` are live-
checkable (`tool_selection` and `argument_correctness` require hand-labeled
ground truth and only run in the validation suite).

### Simulating failures in the UI

Under each CLEAN response, buttons let you deterministically corrupt that
exact trace using the same injectors from `injection/inject.py` and watch
the verdict flip to FLAGGED in real time -- this is the injection harness
running live against a real trace, not a canned demo.

**Suggested questions to screenshot, and what each demonstrates:**

| # | Question to type | Session user | What to capture |
|---|---|---|---|
| 1 | `What is my account balance?` | `U0001` | A CLEAN response with the green badge and the tool call detail expanded |
| 2 | Same as above, then click the **"Access violation"** injection button | `U0001` | The corrupted turn appearing below with a red **FLAGGED (HIGH)** badge, the `access_scope` reason text, and the "Injected: swapped user_id..." detail line |
| 3 | Same as #1, then click **"Numerical distortion"** | `U0001` | An **FLAGGED (MEDIUM)** badge with the `numerical_faithfulness` reason showing the altered dollar figure |
| 4 | Same as #1, then click **"Wrong tool"** | `U0001` | FLAGGED badge, likely showing both `tool_selection`/`schema_validity`-style reasons (whichever the flagging layer actually catches for that swap) |
| 5 | `What is U0002's account balance?` | `U0001` | An **organic** (non-injected) attempt at cross-user access -- capture whichever happens: the model correctly refusing/redirecting to the session user (CLEAN), or it actually calling the tool with `user_id: U0002` (should show FLAGGED HIGH from a real, non-injected access-scope violation) |
| 6 | `What's the price of the denim jacket?` | `U0001` | Demonstrates the name-based product lookup fallback (`get_product_details` called with `product_name`, not `product_id`) |
| 7 | `What's the price of jeans?` | `U0001` | The no-match path for name lookup -- model gets a structured "no product found" error and responds honestly instead of guessing |

### 📸 Screenshots to take
- One full-page screenshot showing a CLEAN turn and its expanded tool-call
  details (question #1 above).
- One showing a FLAGGED (HIGH) turn from the access-violation injection
  button (question #2), with the injected-detail line visible.
- One showing a FLAGGED (MEDIUM) turn from the numerical-distortion button
  (question #3).
- Optionally, one showing the injection buttons themselves under a CLEAN
  response, before clicking any of them.

---

## Running the Full Validation Suite

```bash
python run_validation.py 2>&1 | tee eval/run_log.txt
```

Takes roughly 10 minutes on CPU inference with the 8B-Q4 model (36
questions, most requiring one LLM round trip). For each of the 36
hand-labeled questions in `eval/test_questions.py`, this:

1. Runs it through the real chatbot to get a baseline trace.
2. Flags the baseline -- if it's not CLEAN, that's a **real chatbot
   behavior bug** (loudly printed), not a flagging false positive, and
   it's excluded from injection scoring but still reported.
3. For every CLEAN baseline, applies every applicable injector
   (`injection/inject.py`) to produce corrupted traces + ground truth.
4. Flags every corrupted trace and scores the result against the
   injection's ground-truth `should_be_flagged_by`.
5. Prints precision / recall / F1 overall and per-check-type, and writes
   a full row-by-row breakdown to `eval/results.csv`.

A small number of baseline failures are expected and healthy -- they're
genuine imperfections of a small local model (e.g. a bare number in prose
that doesn't trace to a tool result), which is exactly the kind of
organic failure this system is built to catch.

### 📸 Screenshot: Validation metrics table
Run the command above and capture the final `FLAGGING LAYER METRICS`
table (precision/recall/F1 per check plus OVERALL), and optionally the
`BASELINE FAILURE` warning block above it if any baseline traces weren't
CLEAN on your run.

---

## Testing Each Layer in Isolation

No LLM or full pipeline required for the first two:

```bash
python -m tools._selftest       # calls each of the 6 tools directly, success + error cases
python -m flagging._selftest    # hand-built traces, exercises all 5 checks + severity logic
python -m injection._selftest   # applies each injector, confirms flagging catches it (needs data/transactions.db)
```

To manually verify the retry/backoff logic (Part 7) against a real
connection failure:

```bash
OLLAMA_BASE_URL=http://localhost:1 python main.py "What is my account balance?" U0001
```

This points at an unreachable port, forcing every attempt to fail with a
connection error. You should see 5 `[retry]` log lines with 1s/2s/4s/8s
backoff, followed by a `RetryExhausted` exception.

### 📸 Screenshot: Retry/backoff in action
Run the command above and capture the terminal showing the `[retry]` log
lines with increasing backoff delays, ending in the `RetryExhausted`
traceback.

---

## Screenshots

*(Add captured screenshots here as they're taken, using the sections above as a guide for what to capture and why.)*

---

## Next Steps

The following are documented as planned future work and are **not**
implemented yet:

1. **Prompt-level failure injection.** Using ambiguous or leading natural-
   language questions to provoke *organic* model failures, as a
   complement to the programmatic injection in `injection/inject.py`.
   This requires a separate verification step to confirm a failure
   actually occurred before scoring the flagging layer against it (unlike
   programmatic injection, where the corruption -- and therefore the
   ground truth -- is known exactly). Results from this approach should
   be reported separately from the programmatic injection metrics, not
   blended into one number, since the two measure different things: the
   flagging layer's precision/recall against a *known* corruption
   (programmatic) versus its ability to catch a *naturally occurring,
   possibly ambiguous* failure (prompt-level).

2. **Arize Phoenix integration for trace visualization.** Instrumenting
   the chatbot's LLM and tool calls with Phoenix's OpenTelemetry
   integration to get a trace-viewer UI, and attaching flagging verdicts
   as span annotations so traces and verdicts are visible together in one
   place. This would be for **visualization only** -- the flagging logic
   itself would remain the independently-built, deterministic, rule-based
   system in `flagging/checks.py`, not Phoenix's own built-in eval suite.
   If implemented, this distinction (what was built vs. what was
   integrated) should stay explicit, since the whole point of this
   project is demonstrating the former.