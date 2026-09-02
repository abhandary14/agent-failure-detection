"""
Entry point: runs the full validation suite.

For every hand-labeled question:
  1. Run it through the chatbot to get a baseline trace.
  2. Flag the baseline trace; it should be CLEAN. If not, that's a real
     chatbot bug (loudly reported), not a flagging false positive, and
     the case is excluded from injection scoring.
  3. For each CLEAN baseline, apply every applicable injector to produce
     corrupted traces + ground truth.
  4. Flag every corrupted trace.
  5. Score actual flagged checks against each injection's ground-truth
     should_be_flagged_by.
  6. Print precision/recall/F1 overall and per-check-type, plus a full
     results table, and write eval/results.csv.

Usage:
    python run_validation.py
"""

import csv
from dataclasses import dataclass

import config
from chatbot.agent import Trace, ask
from eval.test_questions import SESSION_USER_ID, TEST_QUESTIONS
from flagging.checks import combine_verdict
from injection.inject import applicable_injectors

ALL_CHECK_NAMES = [
    "tool_selection",
    "argument_correctness",
    "access_scope",
    "numerical_faithfulness",
    "schema_validity",
]


@dataclass
class ResultRow:
    question: str
    injection_type: str
    detail: str
    expected_flags: list[str]
    actual_flags: list[str]
    correct: bool


def run_suite() -> list[ResultRow]:
    rows: list[ResultRow] = []
    baseline_failures: list[str] = []

    for i, case in enumerate(TEST_QUESTIONS, start=1):
        print(f"\n[{i}/{len(TEST_QUESTIONS)}] {case['question']}")
        trace = ask(case["question"], SESSION_USER_ID)

        baseline_verdict = combine_verdict(
            trace,
            session_user_id=SESSION_USER_ID,
            expected_tool=case["expected_tool"],
            expected_args=case["expected_args"],
        )

        if baseline_verdict.status != "CLEAN":
            print(f"  !! BASELINE FAILURE (real chatbot bug, not a flagging false positive): "
                  f"{baseline_verdict.failed_checks} -- {baseline_verdict.reasons}")
            baseline_failures.append(case["question"])
            rows.append(
                ResultRow(
                    question=case["question"],
                    injection_type="(none -- baseline failed)",
                    detail=str(baseline_verdict.reasons),
                    expected_flags=[],
                    actual_flags=baseline_verdict.failed_checks,
                    correct=False,
                )
            )
            continue

        print(f"  Baseline CLEAN. Applying injectors...")
        for label, injector_fn in applicable_injectors(trace):
            try:
                corrupted, ground_truth = injector_fn(trace)
            except ValueError as exc:
                print(f"    skipped {label}: {exc}")
                continue

            corrupted_verdict = combine_verdict(
                corrupted,
                session_user_id=SESSION_USER_ID,
                expected_tool=case["expected_tool"],
                expected_args=case["expected_args"],
            )

            expected_checks = [c.replace("_check", "") for c in ground_truth["should_be_flagged_by"]]
            actual_checks = corrupted_verdict.failed_checks
            caught = bool(set(expected_checks) & set(actual_checks))

            print(f"    {label}: expected {expected_checks} -> got {actual_checks} "
                  f"[{'OK' if caught else 'MISS'}]")

            rows.append(
                ResultRow(
                    question=case["question"],
                    injection_type=ground_truth["injection_type"],
                    detail=ground_truth["detail"],
                    expected_flags=expected_checks,
                    actual_flags=actual_checks,
                    correct=caught,
                )
            )

    if baseline_failures:
        print(f"\n{'=' * 60}")
        print(f"WARNING: {len(baseline_failures)} baseline trace(s) were not CLEAN.")
        print("These indicate real chatbot behavior bugs, not flagging false positives.")
        print("They were excluded from injection scoring.")
        print("=" * 60)

    return rows


def compute_metrics(rows: list[ResultRow]) -> dict:
    """
    Compute precision/recall/F1 overall and per-check-type.

    For each injected case, treat each expected check as a "should fire"
    label and each actual failed check as a "fired" label. A true positive
    is an expected check that fired; a false negative is an expected check
    that did not fire; a false positive is a check that fired but was not
    expected for that specific injection.
    """
    injected_rows = [r for r in rows if r.injection_type != "(none -- baseline failed)"]

    per_check = {name: {"tp": 0, "fp": 0, "fn": 0} for name in ALL_CHECK_NAMES}

    for row in injected_rows:
        expected = set(row.expected_flags)
        actual = set(row.actual_flags)
        for check in ALL_CHECK_NAMES:
            if check in expected and check in actual:
                per_check[check]["tp"] += 1
            elif check in expected and check not in actual:
                per_check[check]["fn"] += 1
            elif check not in expected and check in actual:
                per_check[check]["fp"] += 1

    def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        return precision, recall, f1

    metrics = {}
    total_tp = total_fp = total_fn = 0
    for name, counts in per_check.items():
        p, r, f1 = prf(counts["tp"], counts["fp"], counts["fn"])
        metrics[name] = {"precision": p, "recall": r, "f1": f1, **counts}
        total_tp += counts["tp"]
        total_fp += counts["fp"]
        total_fn += counts["fn"]

    overall_p, overall_r, overall_f1 = prf(total_tp, total_fp, total_fn)
    metrics["overall"] = {
        "precision": overall_p, "recall": overall_r, "f1": overall_f1,
        "tp": total_tp, "fp": total_fp, "fn": total_fn,
    }
    return metrics


def print_metrics(metrics: dict) -> None:
    print(f"\n{'=' * 70}")
    print("FLAGGING LAYER METRICS")
    print("=" * 70)
    print(f"{'Check':<26}{'Precision':>10}{'Recall':>10}{'F1':>10}{'TP':>6}{'FP':>6}{'FN':>6}")
    for name in ALL_CHECK_NAMES + ["overall"]:
        m = metrics[name]
        label = "OVERALL" if name == "overall" else name
        print(f"{label:<26}{m['precision']:>10.2f}{m['recall']:>10.2f}{m['f1']:>10.2f}"
              f"{m['tp']:>6}{m['fp']:>6}{m['fn']:>6}")
    print("=" * 70)


def write_csv(rows: list[ResultRow], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "injection_type", "detail", "expected_flags", "actual_flags", "correct"])
        for row in rows:
            writer.writerow([
                row.question, row.injection_type, row.detail,
                "|".join(row.expected_flags), "|".join(row.actual_flags), row.correct,
            ])
    print(f"\nFull results written to {path}")


def main() -> None:
    rows = run_suite()
    metrics = compute_metrics(rows)
    print_metrics(metrics)
    write_csv(rows, "eval/results.csv")


if __name__ == "__main__":
    main()