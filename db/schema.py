from typing import Optional
import sqlite3
import json
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY,
    saved_at TEXT NOT NULL,
    state_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    status TEXT NOT NULL,
    funnel_steps TEXT NOT NULL,
    businesses_contacted TEXT NOT NULL,
    products_considered TEXT NOT NULL,
    shortlisted TEXT NOT NULL,
    final_product TEXT,
    final_merchant TEXT,
    total REAL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    merchant_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    total REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def has_saved_state(db_path: str) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT COUNT(*) FROM simulation_state")
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_saved_meta(db_path: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT saved_at, state_json FROM simulation_state ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        state = json.loads(row[1])
        return {
            "saved_at": row[0],
            "consumers": len(state.get("consumers", [])),
            "merchants": len([b for b in state.get("businesses", []) if b.get("business_type") == "B2C"]),
            "suppliers": len([b for b in state.get("businesses", []) if b.get("business_type") == "B2B"]),
            "total_orders": state.get("stats", {}).get("total_orders", 0),
        }
    except Exception:
        return None
