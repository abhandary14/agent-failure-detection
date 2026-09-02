"""Tool: get_account_balance -- a user's net spend (completed minus refunded)."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call


def get_account_balance(user_id: str) -> dict[str, Any]:
    """
    Compute a user's net lifetime spend: the sum of their completed
    transaction amounts minus the sum of their refunded transaction amounts.
    "Balance" here means net spend, not a stored account credit -- this
    schema has no wallet/credit concept, so it is defined from transaction
    history instead.

    Args:
        user_id: The user's ID, e.g. "U0001".

    Returns:
        On success: {"user_id": str, "total_completed": float,
                      "total_refunded": float, "net_balance": float}
        On failure: {"error": str}
    """
    args = {"user_id": user_id}

    with timed_call() as t:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            if cur.fetchone() is None:
                result = {"error": f"No user found with user_id '{user_id}'."}
            else:
                cur.execute(
                    """
                    SELECT status, COALESCE(SUM(amount), 0)
                    FROM transactions
                    WHERE user_id = ? AND status IN ('completed', 'refunded')
                    GROUP BY status
                    """,
                    (user_id,),
                )
                totals = {status: total for status, total in cur.fetchall()}
                total_completed = round(totals.get("completed", 0), 2)
                total_refunded = round(totals.get("refunded", 0), 2)
                result = {
                    "user_id": user_id,
                    "total_completed": total_completed,
                    "total_refunded": total_refunded,
                    "net_balance": round(total_completed - total_refunded, 2),
                }
        finally:
            conn.close()

    log_tool_call("get_account_balance", args, result, t.duration_ms)
    return result