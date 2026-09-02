"""
Programmatic failure injection: takes a CLEAN trace and deliberately
corrupts it in controlled, documented ways, returning both the corrupted
trace and a ground-truth record describing exactly what was corrupted.
This ground truth is what the validation harness scores the flagging
layer against.

Each injector deep-copies the trace and never mutates the original.
"""

import copy
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chatbot.agent import Trace
from flagging.checks import (
    _ISO_DATE_PATTERN,
    _PROSE_DATE_PATTERN,
    _UUID_PATTERN,
    _collect_result_numbers,
)
from tools.db import get_connection
from tools.schemas import TOOL_DISPATCH

InjectionRecord = dict[str, Any]


def _other_valid_user_id(exclude: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id != ? ORDER BY RANDOM() LIMIT 1", (exclude,)
        ).fetchone()
    finally:
        conn.close()
    return row["user_id"]


def _other_valid_product_id(exclude: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT product_id FROM products WHERE product_id != ? ORDER BY RANDOM() LIMIT 1",
            (exclude,),
        ).fetchone()
    finally:
        conn.close()
    return row["product_id"]


def inject_wrong_tool(trace: Trace) -> tuple[Trace, InjectionRecord]:
    """
    Swap the called tool for a different valid tool, re-executing it with
    the same arguments where they happen to overlap (dropping args the
    new tool doesn't accept). This simulates the model picking the wrong
    data source for the question.

    Operates on the LAST tool call, not the first: if an earlier call was
    rejected by the tool's own input validation and the model retried with
    a corrected call, the final response is grounded in that later call --
    corrupting an earlier, already-abandoned call wouldn't actually change
    what the model's answer was based on.
    """
    if not trace.tool_calls:
        raise ValueError("Cannot inject_wrong_tool: trace has no tool calls.")

    corrupted = copy.deepcopy(trace)
    call = corrupted.tool_calls[-1]
    original_tool = call.name

    candidate_tools = [name for name in TOOL_DISPATCH if name != original_tool]
    new_tool = random.choice(candidate_tools)

    call.name = new_tool
    # Arguments are deliberately left as-is (from the original tool) --
    # this is the point of the injection: a plausible-looking call to the
    # wrong tool, which may also trip schema_validity if the new tool
    # doesn't accept these argument names.

    record: InjectionRecord = {
        "injection_type": "wrong_tool",
        "detail": f"swapped tool '{original_tool}' for '{new_tool}', arguments left unchanged",
        "should_be_flagged_by": ["tool_selection_check", "schema_validity_check"],
    }
    return corrupted, record


def inject_wrong_argument(trace: Trace, arg_type: str) -> tuple[Trace, InjectionRecord]:
    """
    Corrupt a specific argument type in the first tool call:
      - "date_shift": shift start_date (and end_date, if present) by a
        random 5-30 day offset.
      - "wrong_id": substitute a different valid product_id or user_id.
      - "wrong_limit": change a limit value to a different positive int.

    Operates on the LAST tool call, not the first -- see inject_wrong_tool
    for why (a self-corrected retry means the final response is grounded
    in the later call, not an earlier abandoned attempt).
    """
    if not trace.tool_calls:
        raise ValueError("Cannot inject_wrong_argument: trace has no tool calls.")

    corrupted = copy.deepcopy(trace)
    call = corrupted.tool_calls[-1]
    args = call.arguments

    if arg_type == "date_shift":
        if "start_date" not in args:
            raise ValueError(f"Tool '{call.name}' has no start_date argument to shift.")
        offset_days = random.choice([-30, -14, -7, 7, 14, 30])
        original_start = args["start_date"]
        new_start = (
            datetime.strptime(original_start, "%Y-%m-%d") + timedelta(days=offset_days)
        ).strftime("%Y-%m-%d")
        args["start_date"] = new_start
        detail = f"shifted start_date from {original_start} to {new_start} ({offset_days:+d} days)"

    elif arg_type == "wrong_id":
        if "product_id" in args:
            original = args["product_id"]
            args["product_id"] = _other_valid_product_id(exclude=original)
            detail = f"substituted product_id '{original}' with '{args['product_id']}'"
        elif "user_id" in args:
            original = args["user_id"]
            args["user_id"] = _other_valid_user_id(exclude=original)
            detail = f"substituted user_id '{original}' with '{args['user_id']}'"
            # Substituting user_id is *also* a genuine access-scope violation
            # (the call now uses a different real user's ID than the session
            # user), not just an argument-correctness issue -- both checks
            # legitimately should catch this, so both are declared here
            # rather than under-declaring and penalizing the flagging layer
            # for correctly catching a real problem.
            return corrupted, {
                "injection_type": "wrong_argument",
                "detail": detail,
                "should_be_flagged_by": ["argument_correctness_check", "access_scope_check"],
            }
        else:
            raise ValueError(f"Tool '{call.name}' has no product_id/user_id argument to corrupt.")

    elif arg_type == "wrong_limit":
        if "limit" not in args:
            raise ValueError(f"Tool '{call.name}' has no limit argument to corrupt.")
        original = args["limit"]
        # The model (via Ollama) sometimes emits limit as a numeric string
        # (e.g. "5") rather than an int -- coerce before comparing/offsetting
        # so this injector doesn't crash on a type it doesn't control.
        original_numeric = int(original) if isinstance(original, str) else original
        new_limit = original_numeric + (
            random.choice([-2, 3, 5]) if original_numeric > 2 else 5
        )
        args["limit"] = new_limit
        detail = f"changed limit from {original} to {new_limit}"

    else:
        raise ValueError(f"Unknown arg_type '{arg_type}'.")

    record: InjectionRecord = {
        "injection_type": "wrong_argument",
        "detail": detail,
        "should_be_flagged_by": ["argument_correctness_check"],
    }
    return corrupted, record


def inject_access_violation(trace: Trace) -> tuple[Trace, InjectionRecord]:
    """
    Replace the user_id argument in the first user-scoped tool call with
    a different real user's ID, simulating the model leaking another
    user's data into the session's response.
    """
    user_scoped_calls = [c for c in trace.tool_calls if "user_id" in c.arguments]
    if not user_scoped_calls:
        raise ValueError("Cannot inject_access_violation: no user-scoped tool call in trace.")

    corrupted = copy.deepcopy(trace)
    # find the same call in the deep copy by matching position
    idx = trace.tool_calls.index(user_scoped_calls[0])
    call = corrupted.tool_calls[idx]

    original_user_id = call.arguments["user_id"]
    new_user_id = _other_valid_user_id(exclude=original_user_id)
    call.arguments["user_id"] = new_user_id

    record: InjectionRecord = {
        "injection_type": "access_violation",
        "detail": f"swapped user_id '{original_user_id}' (session user) for '{new_user_id}'",
        # A swapped user_id is simultaneously a real access-scope violation
        # AND a real argument mismatch against expected_args (which pins
        # user_id to the session user) -- both checks correctly catching it
        # is accurate detection, not double-counting, so both are declared.
        "should_be_flagged_by": ["access_scope_check", "argument_correctness_check"],
    }
    return corrupted, record


_RESPONSE_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])-?\$?\d[\d,]*\.?\d*")


def inject_numerical_distortion(trace: Trace) -> tuple[Trace, InjectionRecord]:
    """
    Alter a number in the final response text so it no longer matches
    any tool call result, simulating the model misstating a fetched
    figure.

    Only considers matches that are not part of a date substring (using
    the same ISO/prose date patterns numerical_faithfulness_check strips)
    and that currently DO trace back to a tool result -- distorting a
    number the checker already ignores (e.g. a bare year mentioned in
    prose) would make the injection invisible to the very check it's
    meant to test.
    """
    result_numbers: list[float] = []
    for call in trace.tool_calls:
        _collect_result_numbers(call.result, result_numbers)
    tolerance = 0.01

    excluded_spans = [
        m.span()
        for pattern in (_ISO_DATE_PATTERN, _PROSE_DATE_PATTERN, _UUID_PATTERN)
        for m in pattern.finditer(trace.final_response)
    ]

    def inside_excluded_span(start: int, end: int) -> bool:
        return any(e_start <= start and end <= e_end for e_start, e_end in excluded_spans)

    target_match = None
    for m in _RESPONSE_NUMBER_PATTERN.finditer(trace.final_response):
        if inside_excluded_span(*m.span()):
            continue
        cleaned = m.group().replace("$", "").replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if any(abs(value - r) <= tolerance for r in result_numbers):
            target_match = m
            break

    if target_match is None:
        raise ValueError(
            "Cannot inject_numerical_distortion: no tool-result-traceable number "
            "found in final_response."
        )

    corrupted = copy.deepcopy(trace)
    original_text = target_match.group()
    cleaned = original_text.replace("$", "").replace(",", "")
    original_value = float(cleaned)
    distorted_value = round(original_value + random.choice([-500, -100, 100, 500, 1000]), 2)

    prefix = "$" if original_text.startswith("$") else ""
    distorted_text = f"{prefix}{distorted_value:,.2f}" if "." in original_text else f"{prefix}{int(distorted_value)}"

    corrupted.final_response = (
        trace.final_response[: target_match.start()]
        + distorted_text
        + trace.final_response[target_match.end():]
    )

    record: InjectionRecord = {
        "injection_type": "numerical_distortion",
        "detail": f"altered response number from {original_text} to {distorted_text}",
        "should_be_flagged_by": ["numerical_faithfulness_check"],
    }
    return corrupted, record


def applicable_injectors(trace: Trace) -> list[tuple[str, Any]]:
    """
    Return the (label, injector_fn) pairs applicable to this trace, based
    on its LAST tool call's arguments (see inject_wrong_tool's docstring
    for why the last call, not the first). injector_fn takes a Trace and
    returns (corrupted_trace, ground_truth_record), same as every injector
    above. Shared by run_validation.py and the UI server so both agree on
    what's applicable to a given trace.
    """
    if not trace.tool_calls:
        return []

    call = trace.tool_calls[-1]
    args = call.arguments
    injectors: list[tuple[str, Any]] = [("wrong_tool", lambda t: inject_wrong_tool(t))]

    if "start_date" in args:
        injectors.append(("wrong_argument:date_shift", lambda t: inject_wrong_argument(t, "date_shift")))
    if "product_id" in args or "user_id" in args:
        injectors.append(("wrong_argument:wrong_id", lambda t: inject_wrong_argument(t, "wrong_id")))
    if "limit" in args:
        injectors.append(("wrong_argument:wrong_limit", lambda t: inject_wrong_argument(t, "wrong_limit")))
    if any("user_id" in c.arguments for c in trace.tool_calls):
        injectors.append(("access_violation", lambda t: inject_access_violation(t)))

    if _RESPONSE_NUMBER_PATTERN.search(trace.final_response):
        injectors.append(("numerical_distortion", lambda t: inject_numerical_distortion(t)))

    return injectors