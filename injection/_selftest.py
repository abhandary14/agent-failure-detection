"""
Standalone smoke test for the injection layer -- builds a clean trace by
hand, applies each injector, and confirms both the injection record shape
and that the flagging layer actually flags the check(s) named in
should_be_flagged_by. No LLM involved; requires the synthetic DB to exist
(for looking up alternate valid IDs).

Usage:
    python -m injection._selftest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chatbot.agent import Trace, ToolCallRecord
from flagging.checks import combine_verdict
from injection.inject import (
    inject_access_violation,
    inject_numerical_distortion,
    inject_wrong_argument,
    inject_wrong_tool,
)


def make_clean_trace() -> Trace:
    return Trace(
        trace_id="test",
        question="What was the revenue for P001 in 2025?",
        session_user_id="U0001",
        system_prompt="test system prompt",
        tool_calls=[
            ToolCallRecord(
                name="get_revenue",
                arguments={"product_id": "P001", "start_date": "2025-01-01", "end_date": "2025-12-31"},
                result={"product_id": "P001", "revenue": 1000.0, "transaction_count": 5},
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
        final_response="Revenue for P001 was $1000.00 across 5 transactions.",
    )


def make_user_scoped_trace() -> Trace:
    return Trace(
        trace_id="test2",
        question="What is my account balance?",
        session_user_id="U0001",
        system_prompt="test system prompt",
        tool_calls=[
            ToolCallRecord(
                name="get_account_balance",
                arguments={"user_id": "U0001"},
                result={"user_id": "U0001", "net_balance": 500.0},
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
        final_response="Your account balance is $500.00.",
    )


def check_record_shape(record: dict) -> None:
    assert set(record.keys()) == {"injection_type", "detail", "should_be_flagged_by"}, record
    assert isinstance(record["detail"], str) and record["detail"]
    assert isinstance(record["should_be_flagged_by"], list) and record["should_be_flagged_by"]


def run_case(label: str, trace: Trace, corrupted: Trace, record: dict) -> None:
    """
    Note: this self-test calls combine_verdict without expected_tool /
    expected_args (no eval-set ground truth available here), so
    tool_selection_check and argument_correctness_check are structurally
    skipped regardless of the injection. The full validation harness
    (run_validation.py) has real ground truth and exercises those checks
    properly. Here we only require that AT LEAST ONE of the checks named
    in should_be_flagged_by actually fires -- multiple checks are listed
    per injector precisely because more than one may legitimately catch
    the same corruption (e.g. a wrong-tool swap can trip schema_validity
    even when tool_selection_check itself is unavailable).
    """
    print(f"\n--- {label} ---")
    print("Ground truth:", record)
    check_record_shape(record)

    verdict = combine_verdict(corrupted, session_user_id=trace.session_user_id)
    print("Verdict:", verdict.to_dict())

    expected_checks = {c.replace("_check", "") for c in record["should_be_flagged_by"]}
    actual_failed = set(verdict.failed_checks)
    caught = expected_checks & actual_failed
    assert caught, (
        f"Flagging layer caught NONE of the expected checks {expected_checks} "
        f"(this may be a false negative in the self-test's expected_tool=None "
        f"setup rather than the flagging layer -- see docstring)"
    )
    print(f"PASS -- flagging layer caught: {caught}")


def main() -> None:
    base = make_clean_trace()

    corrupted, record = inject_wrong_tool(base)
    run_case("inject_wrong_tool", base, corrupted, record)

    # argument_correctness_check only fires against known expected_args
    # (eval-mode ground truth), which this standalone self-test doesn't
    # have -- full scoring of these injectors happens in run_validation.py
    # against the hand-labeled eval set. Here we only verify the injector
    # itself produces a well-shaped record and an actually-corrupted trace.
    for arg_type in ("date_shift", "wrong_id"):
        corrupted, record = inject_wrong_argument(make_clean_trace(), arg_type=arg_type)
        print(f"\n--- inject_wrong_argument ({arg_type}) ---")
        print("Ground truth:", record)
        check_record_shape(record)
        assert corrupted.tool_calls[0].arguments != base.tool_calls[0].arguments
        print("PASS -- argument was corrupted (scored against expected_args in run_validation)")

    corrupted, record = inject_access_violation(make_user_scoped_trace())
    run_case("inject_access_violation", make_user_scoped_trace(), corrupted, record)

    corrupted, record = inject_numerical_distortion(make_clean_trace())
    run_case("inject_numerical_distortion", base, corrupted, record)

    print("\nAll injection self-tests passed.")


if __name__ == "__main__":
    main()