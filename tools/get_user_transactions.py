"""Tool: get_user_transactions -- a user's transactions over a date range."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call
from tools.validation import validate_date_range


def get_user_transactions(user_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """
    List a single user's transactions within an inclusive date range.

    Args:
        user_id: The user's ID, e.g. "U0001".
        start_date: Inclusive start of the date range, "YYYY-MM-DD".
        end_date: Inclusive end of the date range, "YYYY-MM-DD".

    Returns:
        On success: {"user_id": str, "start_date": str, "end_date": str,
                      "transactions": [{"transaction_id": str, "product_id": str,
                                         "amount": float, "quantity": int,
                                         "transaction_date": str, "status": str}, ...]}
        On failure: {"error": str}
    """
    args = {"user_id": user_id, "start_date": start_date, "end_date": end_date}

    with timed_call() as t:
        error = validate_date_range(start_date, end_date)
        if error:
            result = {"error": error}
        else:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
                if cur.fetchone() is None:
                    result = {"error": f"No user found with user_id '{user_id}'."}
                else:
                    cur.execute(
                        """
                        SELECT transaction_id, product_id, amount, quantity,
                               transaction_date, status
                        FROM transactions
                        WHERE user_id = ?
                          AND transaction_date BETWEEN ? AND ?
                        ORDER BY transaction_date DESC
                        """,
                        (user_id, start_date, end_date),
                    )
                    rows = cur.fetchall()
                    transactions = [
                        {
                            "transaction_id": row["transaction_id"],
                            "product_id": row["product_id"],
                            "amount": round(row["amount"], 2),
                            "quantity": row["quantity"],
                            "transaction_date": row["transaction_date"],
                            "status": row["status"],
                        }
                        for row in rows
                    ]
                    result = {
                        "user_id": user_id,
                        "start_date": start_date,
                        "end_date": end_date,
                        "transactions": transactions,
                    }
            finally:
                conn.close()

    log_tool_call("get_user_transactions", args, result, t.duration_ms)
    return result