"""
Rule-based flagging layer: analyzes a completed Trace (post-hoc, not the
live call) and produces a structured verdict. Every check here is
deterministic -- exact/tolerant comparison, regex, or set membership.
No LLM-as-judge anywhere in this file, by design.

Each check function returns a CheckResult: {"passed": bool, "reason": str}.
combine_verdict() aggregates all applicable checks into one Verdict.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import config
from chatbot.agent import Trace
from tools.schemas import TOOLS

CheckResult = dict[str, Any]  # {"passed": bool, "reason": str}

TOOL_SCHEMA_BY_NAME = {t["function"]["name"]: t["function"] for t in TOOLS}


def _pass(reason: str) -> CheckResult:
    return {"passed": True, "reason": reason}


def _fail(reason: str) -> CheckResult:
    return {"passed": False, "reason": reason}


def tool_selection_check(trace: Trace, expected_tool: str | None) -> CheckResult:
    """
    Did the model call the expected tool? Only usable in eval mode where
    expected_tool is known from hand-labeled ground truth. In production
    mode (expected_tool=None) this check is skipped upstream in favor of
    a heuristic ("was any tool called at all") -- that heuristic is not
    implemented here since it requires no ground truth by definition and
    isn't meaningfully "checkable" the same way.

    Judged against the LAST tool call, not "was expected_tool called at
    any point": if an earlier call used the expected tool but was rejected
    by its own input validation and the model retried with a DIFFERENT
    tool, the final response is grounded in that different tool -- the
    abandoned first attempt shouldn't count as "the expected tool was
    used" for this trace.
    """
    if expected_tool is None:
        return _pass("No expected_tool provided (production mode) -- check skipped.")

    if not trace.tool_calls:
        return _fail(f"Expected tool '{expected_tool}' but no tool was called.")

    called_tools = [c.name for c in trace.tool_calls]
    last_tool = trace.tool_calls[-1].name
    if last_tool != expected_tool:
        return _fail(f"Expected tool '{expected_tool}' but the final call used {called_tools}.")
    return _pass(f"Expected tool '{expected_tool}' was called.")


def _normalize_value(value: Any) -> Any:
    """Normalize a value for tolerant comparison, handling date-like strings."""
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value


def argument_correctness_check(trace: Trace, expected_args: dict[str, Any] | None) -> CheckResult:
    """
    Do the actual tool call arguments match expected values? Dates are
    normalized before comparison so format variation doesn't cause a
    false mismatch. Only usable when expected_args is known (eval mode).

    Compares against the LAST tool call in the trace, not the first: if
    an earlier call was rejected by the tool's own input validation (e.g.
    a malformed argument type) and the model self-corrected on a later
    call, the final response is grounded in that later call's arguments
    -- checking the first (failed) attempt would judge the wrong data.
    """
    if expected_args is None:
        return _pass("No expected_args provided (production mode) -- check skipped.")

    if not trace.tool_calls:
        return _fail("Expected specific arguments but no tool was called.")

    actual_args = trace.tool_calls[-1].arguments
    mismatches = []
    for key, expected_value in expected_args.items():
        actual_value = actual_args.get(key)
        if _normalize_value(actual_value) != _normalize_value(expected_value):
            mismatches.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")

    if mismatches:
        return _fail("Argument mismatch(es): " + "; ".join(mismatches))
    return _pass("All expected arguments matched.")


def access_scope_check(trace: Trace, session_user_id: str) -> CheckResult:
    """
    For any tool call with a user_id argument, does it match
    session_user_id? Any mismatch is an immediate hard fail -- this is
    a security/privacy boundary, not a quality nit, so it does not
    tolerate any fuzziness or partial credit.
    """
    violations = []
    for call in trace.tool_calls:
        called_user_id = call.arguments.get("user_id")
        if called_user_id is not None and called_user_id != session_user_id:
            violations.append(
                f"{call.name} called with user_id='{called_user_id}' "
                f"but session_user_id='{session_user_id}'"
            )

    if violations:
        return _fail("Access scope violation(s): " + "; ".join(violations))
    return _pass("All user-scoped tool calls used the session user_id.")


_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
# Covers "June 1st to August 31st, 2025" and "August 31, 2025" style prose
# dates. This is a bounded heuristic for the phrasings actually observed
# from the local model, not exhaustive natural-language date parsing --
# other phrasings (e.g. "the 1st of June") can still slip through.
_PROSE_DATE_PATTERN = re.compile(
    rf"\b(?:{_MONTH_NAMES})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\b",
    re.IGNORECASE,
)
# transaction_id values are UUIDs (8-4-4-4-12 hex); a hex segment that
# happens to be all digits (e.g. "416391078" in a UUID) would otherwise
# look like a standalone number preceded by a hyphen, not a letter, so
# the negative-lookbehind in _NUMBER_PATTERN alone doesn't exclude it.
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])-?\$?\d[\d,]*\.?\d*")


def _strip_dates(text: str) -> str:
    """Remove ISO dates, common prose dates, and UUIDs so their component
    digits are never mistaken for standalone numeric claims."""
    text = _ISO_DATE_PATTERN.sub("", text)
    text = _PROSE_DATE_PATTERN.sub("", text)
    text = _UUID_PATTERN.sub("", text)
    return text


def _extract_numbers(text: str) -> list[float]:
    """Extract numeric/currency tokens from text as floats, ignoring
    digits that are part of a date rather than a standalone number."""
    text_without_dates = _strip_dates(text)
    numbers = []
    for match in _NUMBER_PATTERN.findall(text_without_dates):
        cleaned = match.replace("$", "").replace(",", "")
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
    return numbers


def _collect_result_numbers(result: Any, out: list[float]) -> None:
    """
    Recursively collect all numeric values found in a tool result,
    including derived aggregates over list-of-item results (e.g.
    get_user_transactions returns individual transaction rows, and a
    model correctly summarizing "$4,349.43 across 14 transactions, 8
    completed" is faithful arithmetic over that data, not hallucination
    -- so sums, counts, and per-status-value counts are added as valid
    reference numbers too).
    """
    if isinstance(result, bool):
        return
    if isinstance(result, (int, float)):
        out.append(float(result))
    elif isinstance(result, dict):
        for v in result.values():
            _collect_result_numbers(v, out)
    elif isinstance(result, list):
        for v in result:
            _collect_result_numbers(v, out)
        if result and all(isinstance(item, dict) for item in result):
            _add_list_aggregates(result, out)


def _add_list_aggregates(items: list[dict], out: list[float]) -> None:
    """Add sum-per-numeric-field, total count, and count-per-string-value."""
    out.append(float(len(items)))

    numeric_fields = {k for k, v in items[0].items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    for field_name in numeric_fields:
        total = sum(item.get(field_name, 0) for item in items if isinstance(item.get(field_name), (int, float)))
        out.append(round(float(total), 2))

    string_fields = {k for k, v in items[0].items() if isinstance(v, str)}
    for field_name in string_fields:
        value_counts: dict[str, int] = {}
        for item in items:
            value = item.get(field_name)
            if isinstance(value, str):
                value_counts[value] = value_counts.get(value, 0) + 1
        out.extend(float(c) for c in value_counts.values())


def numerical_faithfulness_check(trace: Trace) -> CheckResult:
    """
    Extract numbers from the final response and verify each one appears
    (within rounding tolerance) among the numbers present in the tool
    call results. Catches the model misstating a fetched figure.
    """
    if not trace.tool_calls:
        return _pass("No tool calls were made -- nothing to verify numbers against.")

    response_numbers = _extract_numbers(trace.final_response)
    if not response_numbers:
        return _pass("No numeric values found in final response.")

    result_numbers: list[float] = []
    for call in trace.tool_calls:
        _collect_result_numbers(call.result, result_numbers)

    tolerance = config.NUMERIC_ROUNDING_TOLERANCE
    unverified = []
    for num in response_numbers:
        if not any(abs(num - r) <= tolerance for r in result_numbers):
            unverified.append(num)

    if unverified:
        return _fail(
            f"Response contains numbers not traceable to any tool result "
            f"(within {tolerance} tolerance): {unverified}"
        )
    return _pass("All numbers in the final response are traceable to tool results.")


def schema_validity_check(trace: Trace) -> CheckResult:
    """
    Did every tool call reference a real, declared tool, and did it only
    use parameter names declared in that tool's schema?
    """
    problems = []
    for call in trace.tool_calls:
        schema = TOOL_SCHEMA_BY_NAME.get(call.name)
        if schema is None:
            problems.append(f"'{call.name}' is not a declared tool.")
            continue

        declared_params = set(schema["parameters"]["properties"].keys())
        used_params = set(call.arguments.keys())
        unknown_params = used_params - declared_params
        if unknown_params:
            problems.append(f"'{call.name}' used undeclared parameter(s): {unknown_params}")

        required_params = set(schema["parameters"].get("required", []))
        missing_params = required_params - used_params
        if missing_params:
            problems.append(f"'{call.name}' is missing required parameter(s): {missing_params}")

    if problems:
        return _fail("Schema violation(s): " + "; ".join(problems))
    return _pass("All tool calls used a declared tool and valid parameters.")


# Severity assignment rationale:
#   - access_scope: always HIGH. A user-boundary violation means one user's
#     private financial data was fetched under another user's session --
#     this is a security/privacy incident class, not a quality defect, and
#     must never be downgraded regardless of what else passed.
#   - tool_selection, numerical_faithfulness: MEDIUM. Calling the wrong data
#     source, or stating a number the data doesn't support, materially
#     misleads the user's business decision-making, but does not leak
#     another user's data -- a real but contained failure.
#   - argument_correctness, schema_validity: LOW-MEDIUM, judged per-case.
#     Wrong arguments (e.g. a shifted date range) can range from a harmless
#     off-by-a-day rounding difference to a materially wrong answer; a
#     schema violation (unknown tool/param) is usually a hard functional
#     break for that turn but still doesn't cross a user-privacy boundary
#     the way access_scope does. Defaulted to MEDIUM here since a POC has
#     no reliable signal to distinguish "harmless" from "materially wrong"
#     without re-running the tool with correct args.
_SEVERITY_BY_CHECK = {
    "access_scope": "HIGH",
    "tool_selection": "MEDIUM",
    "numerical_faithfulness": "MEDIUM",
    "argument_correctness": "MEDIUM",
    "schema_validity": "MEDIUM",
}


@dataclass
class Verdict:
    status: str  # "CLEAN" or "FLAGGED"
    failed_checks: list[str]
    reasons: dict[str, str]
    severity: str | None  # highest severity among failed checks, or None if CLEAN

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "failed_checks": self.failed_checks,
            "reasons": self.reasons,
            "severity": self.severity,
        }


_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def combine_verdict(
    trace: Trace,
    session_user_id: str,
    expected_tool: str | None = None,
    expected_args: dict[str, Any] | None = None,
) -> Verdict:
    """Run all applicable checks and combine into one overall verdict."""
    checks = {
        "tool_selection": tool_selection_check(trace, expected_tool),
        "argument_correctness": argument_correctness_check(trace, expected_args),
        "access_scope": access_scope_check(trace, session_user_id),
        "numerical_faithfulness": numerical_faithfulness_check(trace),
        "schema_validity": schema_validity_check(trace),
    }

    failed = {name: result for name, result in checks.items() if not result["passed"]}

    if not failed:
        return Verdict(status="CLEAN", failed_checks=[], reasons={}, severity=None)

    severities = [_SEVERITY_BY_CHECK[name] for name in failed]
    highest_severity = max(severities, key=lambda s: _SEVERITY_ORDER[s])

    return Verdict(
        status="FLAGGED",
        failed_checks=list(failed.keys()),
        reasons={name: result["reason"] for name, result in failed.items()},
        severity=highest_severity,
    )