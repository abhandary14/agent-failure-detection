"""
Standalone smoke test for the tool layer -- calls each of the six tools
directly with known-good and known-bad inputs, no LLM involved.

Usage:
    python -m tools._selftest
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.get_account_balance import get_account_balance
from tools.get_product_details import get_product_details
from tools.get_revenue import get_revenue
from tools.get_spending_by_category import get_spending_by_category
from tools.get_top_products import get_top_products
from tools.get_user_transactions import get_user_transactions


def show(label: str, result: dict) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(result, indent=2, default=str)[:800])


def main() -> None:
    show("get_product_details (valid id)", get_product_details("P001"))
    show("get_product_details (invalid id)", get_product_details("P999"))
    show("get_product_details (valid name, unique)", get_product_details(product_name="Denim Jacket"))
    show("get_product_details (name substring, ambiguous)", get_product_details(product_name="jacket"))
    show("get_product_details (name, no match)", get_product_details(product_name="nonexistent gizmo"))
    show("get_product_details (neither given)", get_product_details())

    show(
        "get_revenue (valid)",
        get_revenue("P001", "2025-09-02", "2026-09-02"),
    )
    show(
        "get_revenue (malformed date)",
        get_revenue("P001", "not-a-date", "2026-09-02"),
    )

    show(
        "get_top_products (valid)",
        get_top_products("2025-09-02", "2026-09-02", 5),
    )
    show(
        "get_top_products (invalid limit)",
        get_top_products("2025-09-02", "2026-09-02", -1),
    )

    show(
        "get_user_transactions (valid)",
        get_user_transactions("U0001", "2025-09-02", "2026-09-02"),
    )
    show(
        "get_user_transactions (nonexistent user)",
        get_user_transactions("U9999", "2025-09-02", "2026-09-02"),
    )

    show("get_account_balance (valid)", get_account_balance("U0001"))
    show("get_account_balance (nonexistent user)", get_account_balance("U9999"))

    show(
        "get_spending_by_category (valid)",
        get_spending_by_category("U0001", "Electronics", "2025-09-02", "2026-09-02"),
    )
    show(
        "get_spending_by_category (invalid category)",
        get_spending_by_category("U0001", "Not A Category", "2025-09-02", "2026-09-02"),
    )

    print("\nAll tool calls completed. Check logs/tool_calls.jsonl for the structured log.")


if __name__ == "__main__":
    main()