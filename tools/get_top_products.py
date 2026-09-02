"""Tool: get_top_products -- best-selling products by revenue over a date range."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call
from tools.validation import validate_date_range


def get_top_products(start_date: str, end_date: str, limit: int) -> dict[str, Any]:
    """
    Rank products by total completed revenue within an inclusive date range.

    Args:
        start_date: Inclusive start of the date range, "YYYY-MM-DD".
        end_date: Inclusive end of the date range, "YYYY-MM-DD".
        limit: Maximum number of products to return (must be a positive integer).

    Returns:
        On success: {"start_date": str, "end_date": str, "limit": int,
                      "products": [{"product_id": str, "name": str,
                                     "category": str, "revenue": float,
                                     "units_sold": int}, ...]}
        On failure: {"error": str}
    """
    args = {"start_date": start_date, "end_date": end_date, "limit": limit}

    with timed_call() as t:
        error = validate_date_range(start_date, end_date)
        if error:
            result = {"error": error}
        elif not isinstance(limit, int) or limit <= 0:
            result = {"error": f"limit must be a positive integer, got '{limit}'."}
        else:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT p.product_id, p.name, p.category,
                           COALESCE(SUM(t.amount), 0) AS revenue,
                           COALESCE(SUM(t.quantity), 0) AS units_sold
                    FROM products p
                    LEFT JOIN transactions t
                        ON t.product_id = p.product_id
                        AND t.status = 'completed'
                        AND t.transaction_date BETWEEN ? AND ?
                    GROUP BY p.product_id
                    ORDER BY revenue DESC
                    LIMIT ?
                    """,
                    (start_date, end_date, limit),
                )
                rows = cur.fetchall()
                products = [
                    {
                        "product_id": row["product_id"],
                        "name": row["name"],
                        "category": row["category"],
                        "revenue": round(row["revenue"], 2),
                        "units_sold": row["units_sold"],
                    }
                    for row in rows
                ]
                result = {
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                    "products": products,
                }
            finally:
                conn.close()

    log_tool_call("get_top_products", args, result, t.duration_ms)
    return result