"""
Generates the synthetic SQLite database used throughout the project:
users, products, and transactions with realistic seasonal variation.

Idempotent: running this script always drops and recreates all tables,
so re-running it never produces duplicates or requires manual cleanup.

Usage:
    python data/generate_synthetic_data.py
"""

import random
import sqlite3
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

# Relative sampling weight per calendar month. Nov/Dec get a holiday-season
# bump (~2.5x an average month) to produce realistic seasonal variation.
MONTH_WEIGHTS = {
    1: 0.8, 2: 0.75, 3: 0.85, 4: 0.9, 5: 0.9, 6: 0.95,
    7: 0.9, 8: 0.9, 9: 1.0, 10: 1.1, 11: 2.2, 12: 2.5,
}

ACCOUNT_STATUS_WEIGHTS = [("active", 0.8), ("inactive", 0.15), ("suspended", 0.05)]
TRANSACTION_STATUS_WEIGHTS = [("completed", 0.80), ("refunded", 0.12), ("pending", 0.08)]

TODAY = date.today()
ONE_YEAR_AGO = TODAY - timedelta(days=365)


def weighted_choice(weighted_options: list[tuple[str, float]]) -> str:
    labels = [label for label, _ in weighted_options]
    weights = [weight for _, weight in weighted_options]
    return random.choices(labels, weights=weights, k=1)[0]


def random_date_between(start: date, end: date) -> date:
    span_days = (end - start).days
    return start + timedelta(days=random.randint(0, span_days))


def random_seasonal_transaction_date() -> date:
    """Pick a date within the last year, weighted so Nov/Dec are busier."""
    months_in_range = []
    cursor = ONE_YEAR_AGO.replace(day=1)
    while cursor <= TODAY:
        months_in_range.append((cursor.year, cursor.month))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    weights = [MONTH_WEIGHTS[m] for _, m in months_in_range]
    year, month = random.choices(months_in_range, weights=weights, k=1)[0]

    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year, 12, 31)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)

    month_start = max(month_start, ONE_YEAR_AGO)
    month_end = min(month_end, TODAY)
    return random_date_between(month_start, month_end)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS users;

        CREATE TABLE users (
            user_id        TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            email          TEXT NOT NULL,
            signup_date    TEXT NOT NULL,
            account_status TEXT NOT NULL
        );

        CREATE TABLE products (
            product_id  TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            price       REAL NOT NULL,
            launch_date TEXT NOT NULL
        );

        CREATE TABLE transactions (
            transaction_id   TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL,
            product_id       TEXT NOT NULL,
            amount           REAL NOT NULL,
            quantity         INTEGER NOT NULL,
            transaction_date TEXT NOT NULL,
            status           TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE INDEX idx_transactions_user_id ON transactions(user_id);
        CREATE INDEX idx_transactions_product_id ON transactions(product_id);
        CREATE INDEX idx_transactions_date ON transactions(transaction_date);
        """
    )


def generate_users(fake: Faker, count: int) -> list[tuple]:
    users = []
    for i in range(1, count + 1):
        user_id = f"U{i:04d}"
        signup = random_date_between(ONE_YEAR_AGO - timedelta(days=365), TODAY)
        users.append(
            (
                user_id,
                fake.name(),
                fake.unique.email(),
                signup.isoformat(),
                weighted_choice(ACCOUNT_STATUS_WEIGHTS),
            )
        )
    return users


PRODUCT_NAMES_BY_CATEGORY = {
    "Electronics": ["Wireless Earbuds", "4K Monitor", "Mechanical Keyboard", "Bluetooth Speaker"],
    "Home": ["Ceramic Cookware Set", "Robot Vacuum", "Air Purifier", "Memory Foam Pillow"],
    "Apparel": ["Running Shoes", "Denim Jacket", "Wool Sweater", "Rain Jacket"],
    "Books": ["Mystery Novel Bundle", "Cookbook Collection", "History of Science", "Sci-Fi Anthology"],
    "Beauty": ["Vitamin C Serum", "Hair Dryer", "Skincare Gift Set", "Electric Shaver"],
}


def generate_products(count: int) -> list[tuple]:
    products = []
    product_num = 1
    categories = config.PRODUCT_CATEGORIES
    names_pool = []
    for category in categories:
        for name in PRODUCT_NAMES_BY_CATEGORY[category]:
            names_pool.append((category, name))

    random.shuffle(names_pool)
    for category, name in names_pool[:count]:
        product_id = f"P{product_num:03d}"
        price = round(random.uniform(9.99, 499.99), 2)
        launch = random_date_between(ONE_YEAR_AGO - timedelta(days=730), ONE_YEAR_AGO)
        products.append((product_id, name, category, price, launch.isoformat()))
        product_num += 1
    return products


def generate_transactions(count: int, user_ids: list[str], products: list[tuple]) -> list[tuple]:
    transactions = []
    product_by_id = {p[0]: p for p in products}
    product_ids = list(product_by_id.keys())

    for _ in range(count):
        transaction_id = str(uuid.uuid4())
        user_id = random.choice(user_ids)
        product_id = random.choice(product_ids)
        price = product_by_id[product_id][3]
        quantity = random.choices([1, 2, 3, 4], weights=[0.7, 0.2, 0.07, 0.03], k=1)[0]
        noise = random.uniform(0.97, 1.0)  # small discount noise, never markup
        amount = round(price * quantity * noise, 2)
        txn_date = random_seasonal_transaction_date()
        status = weighted_choice(TRANSACTION_STATUS_WEIGHTS)

        transactions.append(
            (transaction_id, user_id, product_id, amount, quantity, txn_date.isoformat(), status)
        )
    return transactions


def print_summary(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products")
    product_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM transactions")
    txn_count = cur.fetchone()[0]

    cur.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM transactions")
    min_date, max_date = cur.fetchone()

    cur.execute(
        """
        SELECT strftime('%Y-%m', transaction_date) AS month, COUNT(*)
        FROM transactions
        GROUP BY month
        ORDER BY month
        """
    )
    monthly_counts = cur.fetchall()

    print("=" * 60)
    print("SYNTHETIC DATA GENERATION COMPLETE")
    print("=" * 60)
    print(f"Users:        {user_count}")
    print(f"Products:     {product_count}")
    print(f"Transactions: {txn_count}")
    print(f"Date range:   {min_date} to {max_date}")
    print()
    print("Transactions per month:")
    for month, cnt in monthly_counts:
        bar = "#" * (cnt // 20)
        print(f"  {month}  {cnt:5d}  {bar}")
    print("=" * 60)


def main() -> None:
    random.seed(config.RANDOM_SEED)
    fake = Faker()
    Faker.seed(config.RANDOM_SEED)

    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    try:
        create_schema(conn)

        users = generate_users(fake, config.NUM_USERS)
        conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", users)

        products = generate_products(config.NUM_PRODUCTS)
        conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", products)

        user_ids = [u[0] for u in users]
        transactions = generate_transactions(config.NUM_TRANSACTIONS, user_ids, products)
        conn.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)", transactions
        )

        conn.commit()
        print_summary(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
