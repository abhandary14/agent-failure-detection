"""Tool: get_revenue -- total revenue for a product over a date range."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call
from tools.validation import validate_date_range


def get_revenue(product_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """
    Compute total revenue (sum of completed transaction amounts) for a single
    product within an inclusive date range.

    Args:
        product_id: The product's ID, e.g. "P001".
        start_date: Inclusive start of the date range, "YYYY-MM-DD".
        end_date: Inclusive end of the date range, "YYYY-MM-DD".

    Returns:
        On success: {"product_id": str, "start_date": str, "end_date": str,
                      "revenue": float, "transaction_count": int}
        On failure: {"error": str}
    """
    args = {"product_id": product_id, "start_date": start_date, "end_date": end_date}

    with timed_call() as t:
        error = validate_date_range(start_date, end_date)
        if error:
            result = {"error": error}
        else:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM products WHERE product_id = ?", (product_id,))
                if cur.fetchone() is None:
                    result = {"error": f"No product found with product_id '{product_id}'."}
                else:
                    cur.execute(
                        """
                        SELECT COALESCE(SUM(amount), 0), COUNT(*)
                        FROM transactions
                        WHERE product_id = ?
                          AND status = 'completed'
                          AND transaction_date BETWEEN ? AND ?
                        """,
                        (product_id, start_date, end_date),
                    )
                    revenue, count = cur.fetchone()
                    result = {
                        "product_id": product_id,
                        "start_date": start_date,
                        "end_date": end_date,
                        "revenue": round(revenue, 2),
                        "transaction_count": count,
                    }
            finally:
                conn.close()

    log_tool_call("get_revenue", args, result, t.duration_ms)
    return result