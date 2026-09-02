"""
Hand-labeled test set: 30-50 natural language questions covering all six
tools, each with ground-truth expected_tool and expected_args.

Most questions use explicit dates so the ground truth is stable regardless
of when the suite runs. A few use relative phrasing ("this month", "last
30 days") with expected_args computed from today's date at import time --
these exercise the "inject current date into system prompt" requirement
from Part 3, and are marked with a comment.

Session user for all user-scoped questions is U0001 unless noted.
"""

from datetime import date, timedelta

TODAY = date.today()
SESSION_USER_ID = "U0001"
OTHER_USER_ID = "U0002"

_30_DAYS_AGO = (TODAY - timedelta(days=30)).isoformat()
_TODAY_STR = TODAY.isoformat()
_YEAR_START = date(TODAY.year, 1, 1).isoformat()

TEST_QUESTIONS = [
    # --- get_revenue ---
    {
        "question": "What was the total revenue for product P001 between 2025-01-01 and 2025-12-31?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P001", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    },
    {
        "question": "How much revenue did the 4K Monitor (P008) generate from 2025-06-01 to 2025-08-31?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P008", "start_date": "2025-06-01", "end_date": "2025-08-31"},
    },
    {
        "question": "Show me revenue for P015 for the whole of 2025.",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P015", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    },
    {
        "question": "What did P003 earn us between 2025-11-01 and 2025-12-31?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P003", "start_date": "2025-11-01", "end_date": "2025-12-31"},
    },
    {
        "question": "Total revenue for the Wireless Earbuds (P009) from 2025-03-15 through 2025-04-15?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P009", "start_date": "2025-03-15", "end_date": "2025-04-15"},
    },
    {
        # relative-date question -- exercises system-prompt date injection
        "question": "What has product P001 earned in the last 30 days?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P001", "start_date": _30_DAYS_AGO, "end_date": _TODAY_STR},
    },

    # --- get_top_products ---
    {
        "question": "What were the top 5 products by revenue between 2025-01-01 and 2025-12-31?",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-01-01", "end_date": "2025-12-31", "limit": 5},
    },
    {
        "question": "Give me the top 3 best-selling products from 2025-11-01 to 2025-12-31.",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-11-01", "end_date": "2025-12-31", "limit": 3},
    },
    {
        "question": "List the top 10 products by revenue for Q1 2025 (2025-01-01 to 2025-03-31).",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-01-01", "end_date": "2025-03-31", "limit": 10},
    },
    {
        "question": "What's our single best-selling product between 2025-06-01 and 2025-06-30? Just show the top 1.",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-06-01", "end_date": "2025-06-30", "limit": 1},
    },
    {
        "question": "Top 20 products by revenue from 2025-01-01 to 2025-12-31.",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-01-01", "end_date": "2025-12-31", "limit": 20},
    },
    {
        # relative-date question
        "question": "What were the top 5 products from the start of this year through today?",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": _YEAR_START, "end_date": _TODAY_STR, "limit": 5},
    },

    # --- get_user_transactions ---
    {
        "question": f"Show me {SESSION_USER_ID}'s transactions between 2025-01-01 and 2025-12-31.",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": "2025-01-01", "end_date": "2025-12-31"},
    },
    {
        "question": "List my transactions from 2025-11-01 to 2025-11-30.",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": "2025-11-01", "end_date": "2025-11-30"},
    },
    {
        "question": "What purchases did I make between 2025-07-01 and 2025-07-31?",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": "2025-07-01", "end_date": "2025-07-31"},
    },
    {
        "question": "Pull up my order history for 2025-01-01 through 2025-06-30.",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": "2025-01-01", "end_date": "2025-06-30"},
    },
    {
        # relative-date question
        "question": "What have I bought in the last 30 days?",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": _30_DAYS_AGO, "end_date": _TODAY_STR},
    },

    # --- get_account_balance ---
    {
        "question": "What's my account balance?",
        "expected_tool": "get_account_balance",
        "expected_args": {"user_id": SESSION_USER_ID},
    },
    {
        "question": "How much have I spent net of refunds?",
        "expected_tool": "get_account_balance",
        "expected_args": {"user_id": SESSION_USER_ID},
    },
    {
        "question": "Can you check my current balance for me?",
        "expected_tool": "get_account_balance",
        "expected_args": {"user_id": SESSION_USER_ID},
    },
    {
        "question": "What is my net spend after accounting for any refunds?",
        "expected_tool": "get_account_balance",
        "expected_args": {"user_id": SESSION_USER_ID},
    },

    # --- get_spending_by_category ---
    {
        "question": "How much have I spent on Electronics between 2025-01-01 and 2025-12-31?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Electronics",
            "start_date": "2025-01-01", "end_date": "2025-12-31",
        },
    },
    {
        "question": "What did I spend in the Books category from 2025-09-01 to 2025-09-30?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Books",
            "start_date": "2025-09-01", "end_date": "2025-09-30",
        },
    },
    {
        "question": "My total spend on Home products between 2025-11-01 and 2025-12-31?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Home",
            "start_date": "2025-11-01", "end_date": "2025-12-31",
        },
    },
    {
        "question": "How much did I spend on Beauty products in all of 2025?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Beauty",
            "start_date": "2025-01-01", "end_date": "2025-12-31",
        },
    },
    {
        "question": "What's my Apparel spend from 2025-03-01 to 2025-05-31?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Apparel",
            "start_date": "2025-03-01", "end_date": "2025-05-31",
        },
    },

    # --- get_product_details ---
    {
        "question": "Can you give me details on product P001?",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P001"},
    },
    {
        "question": "What is P008 and how much does it cost?",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P008"},
    },
    {
        "question": "Tell me about the product with ID P014.",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P014"},
    },
    {
        "question": "When was P020 launched and what category is it in?",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P020"},
    },
    {
        "question": "Look up product P011 for me.",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P011"},
    },

    # --- additional mixed-phrasing coverage to reach 30+ ---
    {
        "question": "Revenue breakdown for P002 from 2025-02-01 to 2025-02-28?",
        "expected_tool": "get_revenue",
        "expected_args": {"product_id": "P002", "start_date": "2025-02-01", "end_date": "2025-02-28"},
    },
    {
        "question": "Which 5 products sold the most between 2025-04-01 and 2025-04-30?",
        "expected_tool": "get_top_products",
        "expected_args": {"start_date": "2025-04-01", "end_date": "2025-04-30", "limit": 5},
    },
    {
        "question": "What transactions did I have in October 2025 (2025-10-01 to 2025-10-31)?",
        "expected_tool": "get_user_transactions",
        "expected_args": {"user_id": SESSION_USER_ID, "start_date": "2025-10-01", "end_date": "2025-10-31"},
    },
    {
        "question": "Details for the product P019, please.",
        "expected_tool": "get_product_details",
        "expected_args": {"product_id": "P019"},
    },
    {
        "question": "My spend on Electronics in Q4 2025 (2025-10-01 to 2025-12-31)?",
        "expected_tool": "get_spending_by_category",
        "expected_args": {
            "user_id": SESSION_USER_ID, "category": "Electronics",
            "start_date": "2025-10-01", "end_date": "2025-12-31",
        },
    },
]