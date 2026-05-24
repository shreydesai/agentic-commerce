import os
import json
import tempfile
import pytest
from db.schema import init_db, has_saved_state, get_saved_meta
from db.persistence import save_simulation, load_simulation, save_transaction, load_transactions


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test.db")


def sample_state():
    return {
        "running": False,
        "consumers": [{"agent_id": "c1", "name": "Alice", "total_spent": 49.99}],
        "businesses": [
            {"agent_id": "b1", "name": "TechStore", "business_type": "B2C", "total_revenue": 49.99},
            {"agent_id": "s1", "name": "Supplier", "business_type": "B2B", "total_revenue": 0},
        ],
        "stats": {"total_orders": 1, "total_revenue": 49.99},
    }


def sample_transaction():
    return {
        "transaction_id": "TXN-TEST01",
        "consumer_id": "c1",
        "consumer_name": "Alice",
        "status": "completed",
        "funnel_steps": [{"stage": "discovering", "details": "Started"}],
        "businesses_contacted": ["b1"],
        "products_considered": [{"sku": "T-001", "name": "Widget"}],
        "shortlisted": [{"sku": "T-001", "name": "Widget"}],
        "final_product": "Widget",
        "final_merchant": "TechStore",
        "total": 49.99,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:01:00",
    }


# ── Schema / init ───────────────────────────────────────────────

def test_init_db_creates_tables(tmp_db):
    conn = init_db(tmp_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "simulation_state" in tables
    assert "transactions" in tables
    assert "orders" in tables
    conn.close()


def test_has_saved_state_false_when_empty(tmp_db):
    init_db(tmp_db).close()
    assert has_saved_state(tmp_db) is False


def test_has_saved_state_true_after_save(tmp_db):
    save_simulation(sample_state(), tmp_db)
    assert has_saved_state(tmp_db) is True


def test_has_saved_state_returns_false_for_nonexistent_db(tmp_path):
    assert has_saved_state(str(tmp_path / "nope.db")) is False


# ── Save / load state ───────────────────────────────────────────

def test_save_and_load_state(tmp_db):
    state = sample_state()
    save_simulation(state, tmp_db)
    loaded = load_simulation(tmp_db)
    assert loaded is not None
    assert loaded["stats"]["total_orders"] == 1
    assert loaded["consumers"][0]["name"] == "Alice"


def test_load_returns_none_when_no_state(tmp_db):
    init_db(tmp_db).close()
    result = load_simulation(tmp_db)
    assert result is None


def test_save_multiple_keeps_latest(tmp_db):
    save_simulation({"stats": {"total_orders": 1}}, tmp_db)
    save_simulation({"stats": {"total_orders": 5}}, tmp_db)
    loaded = load_simulation(tmp_db)
    assert loaded["stats"]["total_orders"] == 5


def test_get_saved_meta(tmp_db):
    save_simulation(sample_state(), tmp_db)
    meta = get_saved_meta(tmp_db)
    assert meta is not None
    assert meta["consumers"] == 1
    assert meta["merchants"] == 1   # 1 B2C
    assert meta["suppliers"] == 1   # 1 B2B
    assert meta["total_orders"] == 1
    assert "saved_at" in meta


# ── Transactions ────────────────────────────────────────────────

def test_save_and_load_transaction(tmp_db):
    txn = sample_transaction()
    save_transaction(txn, tmp_db)
    loaded = load_transactions(tmp_db)
    assert len(loaded) == 1
    assert loaded[0]["transaction_id"] == "TXN-TEST01"
    assert loaded[0]["status"] == "completed"
    assert loaded[0]["total"] == pytest.approx(49.99)


def test_transaction_funnel_steps_deserialize(tmp_db):
    txn = sample_transaction()
    save_transaction(txn, tmp_db)
    loaded = load_transactions(tmp_db)
    assert isinstance(loaded[0]["funnel_steps"], list)
    assert loaded[0]["funnel_steps"][0]["stage"] == "discovering"


def test_transaction_upsert(tmp_db):
    txn = sample_transaction()
    save_transaction(txn, tmp_db)
    txn["status"] = "abandoned"
    save_transaction(txn, tmp_db)
    loaded = load_transactions(tmp_db)
    assert len(loaded) == 1
    assert loaded[0]["status"] == "abandoned"


def test_load_transactions_empty(tmp_db):
    result = load_transactions(tmp_db)
    assert result == []
