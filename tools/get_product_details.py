"""Tool: get_product_details -- lookup a single product's attributes."""

from typing import Any

from tools.db import get_connection
from tools.logging_utils import log_tool_call, timed_call


def get_product_details(
    product_id: str | None = None, product_name: str | None = None
) -> dict[str, Any]:
    """
    Look up a single product's attributes, by ID or by name.

    Exactly one of product_id / product_name should be given; if both are
    given, product_id takes precedence. Name matching is a case-insensitive
    substring match -- if it matches more than one product, or none, a
    structured error is returned instead of guessing.

    Args:
        product_id: The product's ID, e.g. "P001".
        product_name: The product's name or a substring of it, e.g.
            "Denim Jacket" or "jacket". Only used if product_id is not given.

    Returns:
        On success: {"product_id": str, "name": str, "category": str,
                      "price": float, "launch_date": str}
        On failure: {"error": str}
    """
    args = {"product_id": product_id, "product_name": product_name}

    with timed_call() as t:
        if not product_id and not product_name:
            result = {"error": "Must provide either product_id or product_name."}
        else:
            conn = get_connection()
            try:
                cur = conn.cursor()
                if product_id:
                    cur.execute(
                        "SELECT product_id, name, category, price, launch_date "
                        "FROM products WHERE product_id = ?",
                        (product_id,),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        result = {"error": f"No product found with product_id '{product_id}'."}
                    else:
                        result = _row_to_result(rows[0])
                else:
                    cur.execute(
                        "SELECT product_id, name, category, price, launch_date "
                        "FROM products WHERE name LIKE ?",
                        (f"%{product_name}%",),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        result = {"error": f"No product found matching name '{product_name}'."}
                    elif len(rows) > 1:
                        matches = [{"product_id": r["product_id"], "name": r["name"]} for r in rows]
                        result = {
                            "error": f"Multiple products match '{product_name}'. "
                            f"Specify a product_id instead.",
                            "matches": matches,
                        }
                    else:
                        result = _row_to_result(rows[0])
            finally:
                conn.close()

    log_tool_call("get_product_details", args, result, t.duration_ms)
    return result


def _row_to_result(row: Any) -> dict[str, Any]:
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category"],
        "price": round(row["price"], 2),
        "launch_date": row["launch_date"],
    }