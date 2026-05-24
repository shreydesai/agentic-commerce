from typing import Optional
import sqlite3
import json
from datetime import datetime
from db.schema import init_db


def save_simulation(state: dict, db_path: str):
    conn = init_db(db_path)
    conn.execute(
        "INSERT INTO simulation_state (saved_at, state_json) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), json.dumps(state, default=str)),
    )
    # Keep only last 3 saves
    conn.execute(
        "DELETE FROM simulation_state WHERE id NOT IN (SELECT id FROM simulation_state ORDER BY id DESC LIMIT 3)"
    )
    conn.commit()
    conn.close()


def load_simulation(db_path: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT state_json FROM simulation_state ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return None
    except Exception:
        return None


def save_transaction(txn: dict, db_path: str):
    conn = init_db(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO transactions
           (transaction_id, consumer_id, consumer_name, status, funnel_steps,
            businesses_contacted, products_considered, shortlisted,
            final_product, final_merchant, total, started_at, completed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            txn["transaction_id"],
            txn["consumer_id"],
            txn["consumer_name"],
            txn["status"],
            json.dumps(txn.get("funnel_steps", [])),
            json.dumps(txn.get("businesses_contacted", [])),
            json.dumps(txn.get("products_considered", [])),
            json.dumps(txn.get("shortlisted", [])),
            txn.get("final_product"),
            txn.get("final_merchant"),
            txn.get("total"),
            txn.get("started_at", datetime.utcnow().isoformat()),
            txn.get("completed_at"),
        ),
    )
    conn.commit()
    conn.close()


def load_transactions(db_path: str) -> list[dict]:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT * FROM transactions ORDER BY started_at DESC LIMIT 100")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        for r in rows:
            for field in ("funnel_steps", "businesses_contacted", "products_considered", "shortlisted"):
                r[field] = json.loads(r[field] or "[]")
        return rows
    except Exception:
        return []
