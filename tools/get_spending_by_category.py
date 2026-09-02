"""Tool: get_spending_by_category -- a user's spend in one product category."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call
from tools.validation import validate_date_range


def get_spending_by_category(
    user_id: str, category: str, start_date: str, end_date: str
) -> dict[str, Any]:
    """
    Sum a user's completed-transaction spend within a single product
    category over an inclusive date range.

    Args:
        user_id: The user's ID, e.g. "U0001".
        category: Product category, e.g. "Electronics".
        start_date: Inclusive start of the date range, "YYYY-MM-DD".
        end_date: Inclusive end of the date range, "YYYY-MM-DD".

    Returns:
        On success: {"user_id": str, "category": str, "start_date": str,
                      "end_date": str, "total_spent": float,
                      "transaction_count": int}
        On failure: {"error": str}
    """
    args = {
        "user_id": user_id,
        "category": category,
        "start_date": start_date,
        "end_date": end_date,
    }

    with timed_call() as t:
        error = validate_date_range(start_date, end_date)
        if error:
            result = {"error": error}
        else:
            conn = get_connection()
            try:
                cur = conn.cursor()
                user_exists = (
                    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
                    is not None
                )
                category_exists = (
                    cur.execute(
                        "SELECT 1 FROM products WHERE category = ? LIMIT 1", (category,)
                    ).fetchone()
                    is not None
                )

                if not user_exists:
                    result = {"error": f"No user found with user_id '{user_id}'."}
                elif not category_exists:
                    result = {"error": f"No products found in category '{category}'."}
                else:
                    cur.execute(
                        """
                        SELECT COALESCE(SUM(t.amount), 0), COUNT(*)
                        FROM transactions t
                        JOIN products p ON p.product_id = t.product_id
                        WHERE t.user_id = ?
                          AND p.category = ?
                          AND t.status = 'completed'
                          AND t.transaction_date BETWEEN ? AND ?
                        """,
                        (user_id, category, start_date, end_date),
                    )
                    total, count = cur.fetchone()
                    result = {
                        "user_id": user_id,
                        "category": category,
                        "start_date": start_date,
                        "end_date": end_date,
                        "total_spent": round(total, 2),
                        "transaction_count": count,
                    }
            finally:
                conn.close()

    log_tool_call("get_spending_by_category", args, result, t.duration_ms)
    return result