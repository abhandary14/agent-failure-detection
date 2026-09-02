"""
Standalone smoke test for the flagging layer -- builds a few traces by
hand (no LLM involved) and confirms each check fires as expected.

Usage:
    python -m flagging._selftest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chatbot.agent import Trace, ToolCallRecord
from flagging.checks import combine_verdict


def make_trace(tool_calls: list[ToolCallRecord], final_response: str, session_user_id: str = "U0001") -> Trace:
    return Trace(
        trace_id="test",
        question="test question",
        session_user_id=session_user_id,
        system_prompt="test system prompt",
        tool_calls=tool_calls,
        final_response=final_response,
    )


def show(label: str, verdict) -> None:
    print(f"\n--- {label} ---")
    print(verdict.to_dict())


def main() -> None:
    # 1. Fully clean trace: correct tool, correct args, correct scope, faithful numbers
    clean_trace = make_trace(
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
    verdict = combine_verdict(
        clean_trace,
        session_user_id="U0001",
        expected_tool="get_revenue",
        expected_args={"product_id": "P001", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    show("Clean trace (expect CLEAN)", verdict)
    assert verdict.status == "CLEAN"

    # 2. Access scope violation: wrong user_id used
    scope_violation_trace = make_trace(
        tool_calls=[
            ToolCallRecord(
                name="get_account_balance",
                arguments={"user_id": "U9999"},
                result={"user_id": "U9999", "net_balance": 500.0},
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
        final_response="Your balance is $500.00.",
        session_user_id="U0001",
    )
    verdict = combine_verdict(scope_violation_trace, session_user_id="U0001")
    show("Access scope violation (expect FLAGGED, HIGH)", verdict)
    assert verdict.status == "FLAGGED"
    assert verdict.severity == "HIGH"
    assert "access_scope" in verdict.failed_checks

    # 3. Numerical unfaithfulness: response states a number not in tool result
    unfaithful_trace = make_trace(
        tool_calls=[
            ToolCallRecord(
                name="get_revenue",
                arguments={"product_id": "P001", "start_date": "2025-01-01", "end_date": "2025-12-31"},
                result={"product_id": "P001", "revenue": 1000.0, "transaction_count": 5},
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
        final_response="Revenue for P001 was $9999.99.",
    )
    verdict = combine_verdict(unfaithful_trace, session_user_id="U0001")
    show("Numerical unfaithfulness (expect FLAGGED)", verdict)
    assert verdict.status == "FLAGGED"
    assert "numerical_faithfulness" in verdict.failed_checks

    # 4. Schema violation: undeclared tool
    bad_schema_trace = make_trace(
        tool_calls=[
            ToolCallRecord(
                name="delete_all_users",
                arguments={"confirm": True},
                result={"error": "unknown tool"},
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
        final_response="Done.",
    )
    verdict = combine_verdict(bad_schema_trace, session_user_id="U0001")
    show("Schema violation (expect FLAGGED)", verdict)
    assert verdict.status == "FLAGGED"
    assert "schema_validity" in verdict.failed_checks

    print("\nAll flagging self-tests passed.")


if __name__ == "__main__":
    main()