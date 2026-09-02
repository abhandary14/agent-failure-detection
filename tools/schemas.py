"""
Tool schemas offered to the LLM, in Ollama's tool-calling format (which
mirrors OpenAI's function-calling schema: {"type": "function", "function":
{"name", "description", "parameters": <JSON Schema>}}).

TOOLS is the list passed directly to the chat API. TOOL_DISPATCH maps a
tool name to its Python implementation, used by the chatbot orchestration
loop to actually execute a requested call.
"""

from tools.get_account_balance import get_account_balance
from tools.get_product_details import get_product_details
from tools.get_revenue import get_revenue
from tools.get_spending_by_category import get_spending_by_category
from tools.get_top_products import get_top_products
from tools.get_user_transactions import get_user_transactions

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_revenue",
            "description": (
                "Get total revenue (sum of completed transaction amounts) for a "
                "single product within an inclusive date range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID, e.g. 'P001'."},
                    "start_date": {"type": "string", "description": "Inclusive start date, YYYY-MM-DD."},
                    "end_date": {"type": "string", "description": "Inclusive end date, YYYY-MM-DD."},
                },
                "required": ["product_id", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_products",
            "description": (
                "Rank products by total completed revenue within an inclusive "
                "date range and return the top N."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Inclusive start date, YYYY-MM-DD."},
                    "end_date": {"type": "string", "description": "Inclusive end date, YYYY-MM-DD."},
                    "limit": {"type": "integer", "description": "Maximum number of products to return."},
                },
                "required": ["start_date", "end_date", "limit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_transactions",
            "description": "List a single user's transactions within an inclusive date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID, e.g. 'U0001'."},
                    "start_date": {"type": "string", "description": "Inclusive start date, YYYY-MM-DD."},
                    "end_date": {"type": "string", "description": "Inclusive end date, YYYY-MM-DD."},
                },
                "required": ["user_id", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": (
                "Get a user's net lifetime spend: sum of completed transaction "
                "amounts minus sum of refunded transaction amounts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID, e.g. 'U0001'."},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_by_category",
            "description": (
                "Sum a user's completed-transaction spend within a single "
                "product category over an inclusive date range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID, e.g. 'U0001'."},
                    "category": {"type": "string", "description": "Product category, e.g. 'Electronics'."},
                    "start_date": {"type": "string", "description": "Inclusive start date, YYYY-MM-DD."},
                    "end_date": {"type": "string", "description": "Inclusive end date, YYYY-MM-DD."},
                },
                "required": ["user_id", "category", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": (
                "Look up a single product's attributes (name, category, price, "
                "launch_date) by ID or by name. Provide product_id if known; "
                "otherwise provide product_name to search by name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID, e.g. 'P001'."},
                    "product_name": {
                        "type": "string",
                        "description": "Product name or substring, e.g. 'Denim Jacket'. Used only if product_id is not known.",
                    },
                },
                "required": [],
            },
        },
    },
]

TOOL_DISPATCH = {
    "get_revenue": get_revenue,
    "get_top_products": get_top_products,
    "get_user_transactions": get_user_transactions,
    "get_account_balance": get_account_balance,
    "get_spending_by_category": get_spending_by_category,
    "get_product_details": get_product_details,
}