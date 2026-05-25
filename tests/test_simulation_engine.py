import asyncio
import pytest
from simulation.engine import SimulationEngine


@pytest.fixture
def engine():
    e = SimulationEngine()
    e.initialize()
    return e


def test_engine_initializes_agents(engine):
    assert len(engine.consumers) == 10
    assert len(engine.businesses) == 17  # 10 B2C (5 HQ + 5 new HQ) + 3 imperfect + 4 B2B
    b2c = [b for b in engine.businesses.values() if b.business_type == "B2C"]
    b2b = [b for b in engine.businesses.values() if b.business_type == "B2B"]
    assert len(b2c) == 13
    assert len(b2b) == 4


def test_engine_message_bus_populated(engine):
    for agent_id in engine.consumers:
        assert agent_id in engine.message_bus
    for agent_id in engine.businesses:
        assert agent_id in engine.message_bus


def test_engine_get_state_structure(engine):
    state = engine.get_state()
    assert "running" in state
    assert "consumers" in state
    assert "businesses" in state
    assert "stats" in state
    assert "transactions" in state
    assert state["running"] is False
    assert state["stats"]["total_revenue"] == 0.0
    assert state["stats"]["total_orders"] == 0


def test_engine_consumers_have_merchant_registry(engine):
    for consumer in engine.consumers.values():
        assert len(consumer.business_registry) > 0
        assert consumer.business_registry is engine.businesses


def test_engine_businesses_have_quality_scores(engine):
    for biz in engine.businesses.values():
        assert 0 <= biz.quality_score <= 100

    # Imperfect businesses should have lower scores than perfect ones
    techzone = engine.businesses.get("biz_techzone")
    pixeldrop = engine.businesses.get("biz_pixeldrop")
    if techzone and pixeldrop:
        assert techzone.quality_score > pixeldrop.quality_score


def test_engine_b2c_have_suppliers(engine):
    techzone = engine.businesses.get("biz_techzone")
    assert techzone is not None
    assert "biz_componentscorp" in techzone.supplier_ids


@pytest.mark.asyncio
async def test_engine_start_sets_running(engine):
    try:
        await asyncio.wait_for(engine.start(mode="fresh"), timeout=2.0)
    except asyncio.TimeoutError:
        pass  # expected — agents loop forever
    assert engine.running is True
    await engine.stop()


@pytest.mark.asyncio
async def test_engine_stop_cancels_tasks(engine):
    await asyncio.wait_for(engine.start(mode="fresh"), timeout=1.0) if False else None
    await engine.start(mode="fresh")
    await asyncio.sleep(0.1)
    await engine.stop()
    assert engine.running is False
    assert len(engine.tasks) == 0
    for agent in list(engine.consumers.values()) + list(engine.businesses.values()):
        assert agent.active is False


@pytest.mark.asyncio
async def test_engine_emits_start_event(engine):
    await engine.start(mode="fresh")
    await asyncio.sleep(0.1)
    await engine.stop()
    event = await asyncio.wait_for(engine.event_bus.get(), timeout=2.0)
    assert event.event_type == "simulation_started"


def test_engine_record_transaction(engine):
    txn = {
        "transaction_id": "TXN-TEST01",
        "consumer_id": "consumer_alex",
        "consumer_name": "Alex Chen",
        "status": "completed",
        "funnel_steps": [],
        "businesses_contacted": [],
        "products_considered": [],
        "shortlisted": [],
        "total": 49.99,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:01:00",
    }
    engine.record_transaction(txn)
    assert "TXN-TEST01" in engine.transactions
    assert engine.transactions["TXN-TEST01"]["status"] == "completed"


def test_engine_reset_reinitializes(engine):
    original_txn_count = len(engine.transactions)
    engine.record_transaction({"transaction_id": "TXN-RESET", "consumer_id": "x",
                                "consumer_name": "x", "status": "completed",
                                "funnel_steps": [], "businesses_contacted": [],
                                "products_considered": [], "shortlisted": [],
                                "started_at": "2026-01-01T00:00:00"})
    assert len(engine.transactions) > original_txn_count

    engine.reset()
    assert len(engine.transactions) == 0
    assert len(engine.consumers) == 10
    assert len(engine.businesses) == 17
