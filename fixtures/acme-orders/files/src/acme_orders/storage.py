"""SQLite storage for orders. Totals are stored in euro cents."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    discount_code TEXT,
    total_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS order_lines (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price TEXT NOT NULL
);
"""


def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.executescript(SCHEMA)
    return db


def save_order(db, order, total):
    with db:
        db.execute(
            "INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?)",
            (order.order_id, order.customer_email, order.created_at.isoformat(), order.discount_code, int(total * 100)),
        )
        db.execute("DELETE FROM order_lines WHERE order_id = ?", (order.order_id,))
        db.executemany(
            "INSERT INTO order_lines VALUES (?, ?, ?, ?)",
            [(order.order_id, line.sku, line.quantity, str(line.unit_price)) for line in order.lines],
        )


def get_order(db, order_id):
    row = db.execute(
        "SELECT order_id, customer_email, created_at, discount_code, total_cents FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if row is None:
        return None
    lines = db.execute("SELECT sku, quantity, unit_price FROM order_lines WHERE order_id = ?", (order_id,)).fetchall()
    return {
        "order_id": row[0],
        "customer_email": row[1],
        "created_at": row[2],
        "discount_code": row[3],
        "total_cents": row[4],
        "lines": [{"sku": sku, "quantity": qty, "unit_price": price} for sku, qty, price in lines],
    }


def totals_by_day(db, day):
    return db.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_cents), 0) FROM orders WHERE substr(created_at, 1, 10) = ?",
        (day,),
    ).fetchone()
