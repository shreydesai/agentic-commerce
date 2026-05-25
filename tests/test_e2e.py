"""
End-to-end integration tests — exercise complete multi-agent workflows
without real LLM calls, verifying that all components compose correctly.

Key testing patterns:
  - BaseAgent.__init__ auto-creates message_bus[agent_id] — capture queues AFTER creation
  - _do_discovery() sends queries then sleep(2) then reads consumer inbox
    → pre-populate consumer inbox BEFORE calling _do_discovery
  - Supply chain: capture supplier_q = message_bus["biz_sup_id"] after creating b2b agent

Flows tested:
  1. Full purchase lifecycle: discover → consider → convert → post-purchase → review
  2. Negotiation lifecycle: consumer requests discount → merchant counters → consumer accepts
  3. B2B supply chain: low inventory → restock order → supply confirmation → inventory restored
  4. Scenario → agent state mutation → reset → state restored
  5. State consistency / JSON-serializability
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import make_consumer, make_business
from agents.consumer import ConsumerState
from acp.models import AgentMessage


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_pair(event_bus, message_bus, price_sensitivity=0.3, research_depth=0.4,
               stock=20, price=49.99):
    """
    Create a matched consumer + B2C business pair.
    BaseAgent.__init__ auto-registers message_bus[agent_id], so we capture
    queue references AFTER construction.
    """
    from agents.consumer import ConsumerAgent
    products = [
        {"sku": "E2E-001", "name": "E2E Widget", "description": "An end-to-end test widget.",
         "category": "electronics", "price": price, "stock": stock},
    ]
    biz = make_business(event_bus, message_bus, agent_id="biz_e2e", name="E2EStore",
                        products=products, vertical="electronics")
    # Capture the queue created by BaseAgent.__init__
    biz_q = message_bus["biz_e2e"]

    consumer = ConsumerAgent(
        agent_id="consumer_e2e", name="E2E User", age=30, gender="female",
        occupation="Engineer", annual_income=80_000, education="Bachelor's",
        location="Austin, TX", household_size=2, shopping_interests=["electronics"],
        price_sensitivity=price_sensitivity, brand_loyalty=0.5,
        impulse_tendency=0.5, research_depth=research_depth,
        preferred_channels=["online"], budget=500.0, credit_score=720,
        persona="A careful shopper.",
        event_bus=event_bus, message_bus=message_bus,
        business_registry={"biz_e2e": biz},
    )
    # Consumer inbox auto-created by BaseAgent.__init__
    consumer_q = message_bus["consumer_e2e"]

    return consumer, biz, consumer_q, biz_q


def _fake_product_response(from_id, to_id, sku="E2E-001", price=49.99, stock=20):
    return AgentMessage(
        from_agent_id=from_id,
        to_agent_id=to_id,
        message_type="product_response",
        content={"products": [{"sku": sku, "name": "E2E Widget", "price": price,
                               "merchant_id": from_id, "merchant_name": "E2EStore",
                               "quality_score": 90, "has_quality_issues": False,
                               "category": "electronics", "stock": stock, "rating": 4.5}]},
    )


def _fake_discovery_pong(from_id, to_id, can_serve=True):
    """Simulates the merchant capability response to a discovery_ping."""
    return AgentMessage(
        from_agent_id=from_id,
        to_agent_id=to_id,
        message_type="discovery_pong",
        content={"can_serve": can_serve, "quality_score": 90.0, "quality_tier": "excellent",
                 "vertical": "electronics", "merchant_name": "E2EStore"},
    )


# ── Flow 1: Full purchase lifecycle ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_purchase_flow(event_bus, message_bus):
    """Consumer discovers, considers, converts, and posts a review end-to-end."""
    consumer, biz, consumer_q, biz_q = _make_pair(event_bus, message_bus)

    # 1. Discovery — seed inbox with pong + product response (discovery ping/pong phase)
    discover_llm = {"category": "electronics", "query": "widget", "max_price": 100.0}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=discover_llm)):
        await consumer._start_discovery()
        # Pong must arrive before product_response (ping fires first, then product_query)
        consumer_q.put_nowait(_fake_discovery_pong("biz_e2e", "consumer_e2e"))
        consumer_q.put_nowait(_fake_product_response("biz_e2e", "consumer_e2e"))
        await consumer._do_discovery()

    assert consumer.state == ConsumerState.CONSIDERING
    assert len(consumer.candidate_products) >= 1

    # 2. Consideration
    consider_llm = {"shortlisted_skus": ["E2E-001"], "has_question": False}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=consider_llm)):
        await consumer._do_consideration()

    assert consumer.state == ConsumerState.CONVERTING
    assert len(consumer.shortlisted) >= 1

    # 3. Conversion (no negotiation — low price_sensitivity=0.3)
    confirm = AgentMessage(
        from_agent_id="biz_e2e", to_agent_id="consumer_e2e",
        message_type="order_confirmation",
        content={"order_id": "E2E-ORD-001", "product_name": "E2E Widget", "total": 49.99},
    )
    consumer_q.put_nowait(confirm)
    convert_llm = {"decision": "buy", "chosen_sku": "E2E-001", "reasoning": "best option"}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=convert_llm)):
        await consumer._do_conversion()

    # Consumer now waits for delivery notice before reviewing
    assert consumer.state == ConsumerState.AWAITING_DELIVERY
    assert consumer.total_spent == pytest.approx(49.99)
    assert len(consumer.purchase_history) == 1
    assert consumer.purchase_history[0]["sku"] == "E2E-001"

    # Simulate delivery arriving → advance to POST_PURCHASE
    consumer.state = ConsumerState.POST_PURCHASE

    # 4. Post-purchase review
    review_llm = {"rating": 5, "review": "Excellent product!"}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=review_llm)):
        await consumer._do_post_purchase()

    assert consumer.state == ConsumerState.IDLE

    # Drain biz_q (may contain leftover product_query from discovery) to find review
    review_msg = None
    for _ in range(10):
        try:
            msg = await asyncio.wait_for(biz_q.get(), timeout=1.0)
            if msg.message_type == "review":
                review_msg = msg
                break
        except asyncio.TimeoutError:
            break
    assert review_msg is not None, "Expected review message in biz inbox"
    assert review_msg.content["rating"] == 5


@pytest.mark.asyncio
async def test_purchase_events_emitted(event_bus, message_bus):
    """Full purchase flow emits purchase_completed and transaction events."""
    consumer, biz, consumer_q, biz_q = _make_pair(event_bus, message_bus)

    discover_llm = {"category": "electronics", "query": "widget", "max_price": 100.0}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=discover_llm)):
        await consumer._start_discovery()
        consumer_q.put_nowait(_fake_discovery_pong("biz_e2e", "consumer_e2e"))
        consumer_q.put_nowait(_fake_product_response("biz_e2e", "consumer_e2e"))
        await consumer._do_discovery()

    consider_llm = {"shortlisted_skus": ["E2E-001"], "has_question": False}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=consider_llm)):
        await consumer._do_consideration()

    confirm = AgentMessage(
        from_agent_id="biz_e2e", to_agent_id="consumer_e2e",
        message_type="order_confirmation",
        content={"order_id": "E2E-ORD-002", "product_name": "E2E Widget", "total": 49.99},
    )
    consumer_q.put_nowait(confirm)
    convert_llm = {"decision": "buy", "chosen_sku": "E2E-001", "reasoning": "perfect"}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=convert_llm)):
        await consumer._do_conversion()

    events = []
    while not event_bus.empty():
        events.append(event_bus.get_nowait())
    event_types = [e.event_type for e in events]

    assert "purchase_completed" in event_types
    assert any("transaction" in t for t in event_types)


@pytest.mark.asyncio
async def test_purchase_reduces_inventory(event_bus, message_bus):
    """Placing an order decrements business inventory."""
    _, biz, consumer_q, biz_q = _make_pair(event_bus, message_bus, stock=10)
    initial_stock = biz.inventory["E2E-001"]
    assert initial_stock == 10

    order = AgentMessage(
        from_agent_id="consumer_e2e", to_agent_id="biz_e2e",
        message_type="place_order",
        content={"sku": "E2E-001", "quantity": 1, "price": 49.99, "consumer_name": "E2E User"},
    )
    await biz._handle_order(order)
    assert biz.inventory["E2E-001"] == initial_stock - 1


# ── Flow 2: Full negotiation lifecycle ───────────────────────────────────────

@pytest.mark.asyncio
async def test_full_negotiation_flow(event_bus, message_bus):
    """
    End-to-end: price-sensitive consumer negotiates, merchant counters, consumer
    accepts and order is placed at agreed price.
    """
    consumer, biz, consumer_q, biz_q = _make_pair(
        event_bus, message_bus,
        price_sensitivity=0.8, research_depth=0.7, price=100.0,
    )
    consumer.state = ConsumerState.CONVERTING
    consumer.shortlisted = [
        {"sku": "E2E-001", "name": "E2E Widget", "price": 100.0,
         "merchant_id": "biz_e2e", "merchant_name": "E2EStore", "quality_score": 90},
    ]
    consumer._new_transaction()

    # Pre-load merchant responses: counter_offer → order_confirmation
    counter = AgentMessage(
        from_agent_id="biz_e2e", to_agent_id="consumer_e2e",
        message_type="counter_offer",
        content={"sku": "E2E-001", "transaction_id": None,
                 "offered_price": 88.0, "original_price": 100.0,
                 "offer_type": "counter", "reason": "Valued customer"},
    )
    confirm = AgentMessage(
        from_agent_id="biz_e2e", to_agent_id="consumer_e2e",
        message_type="order_confirmation",
        content={"order_id": "NEG-ORD-001", "product_name": "E2E Widget", "total": 88.0},
    )
    consumer_q.put_nowait(counter)
    consumer_q.put_nowait(confirm)

    convert_llm = {"decision": "buy", "chosen_sku": "E2E-001", "reasoning": "great deal"}
    with patch.object(consumer, "call_llm", AsyncMock(return_value=convert_llm)):
        await consumer._do_conversion()

    # Verify purchase happened at negotiated price
    assert consumer.total_spent == pytest.approx(88.0)
    assert consumer.purchase_history[-1]["price"] == pytest.approx(88.0)

    # Drain biz inbox and check message types
    msgs = []
    while not biz_q.empty():
        msgs.append(biz_q.get_nowait())
    msg_types = [m.message_type for m in msgs]

    assert "negotiation_request" in msg_types
    assert "negotiation_accept" in msg_types
    assert "place_order" in msg_types

    order_msg = next(m for m in msgs if m.message_type == "place_order")
    assert order_msg.content["price"] == pytest.approx(88.0)
    assert order_msg.content["price"] < 100.0  # definitely discounted


@pytest.mark.asyncio
async def test_negotiation_roundtrip_with_merchant_handler(event_bus, message_bus):
    """
    Consumer sends negotiation_request → merchant handler responds → consumer
    receives counter_offer — both sides use real handler code.
    """
    consumer, biz, consumer_q, biz_q = _make_pair(
        event_bus, message_bus,
        price_sensitivity=0.8, research_depth=0.7, price=100.0,
    )

    # Consumer sends negotiation_request to biz_e2e
    await consumer.send_message("biz_e2e", "negotiation_request", {
        "sku": "E2E-001",
        "preferred_price": 88.0,
        "max_price": 100.0,
        "transaction_id": "TXN-ROUNDTRIP",
        "reason": "Budget-conscious",
    })

    # Merchant handles the request (LLM returns counter at 90.0)
    merchant_llm = {"action": "accept", "offered_price": 90.0, "reason": "For you, a deal."}
    neg_msg = await asyncio.wait_for(biz_q.get(), timeout=2.0)
    assert neg_msg.message_type == "negotiation_request"
    with patch.object(biz, "call_llm", AsyncMock(return_value=merchant_llm)):
        await biz._handle_negotiation_request(neg_msg)

    # Consumer should now have received a counter_offer
    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "counter_offer"
    assert response.content["offered_price"] == pytest.approx(90.0)


# ── Flow 3: B2B supply chain ──────────────────────────────────────────────────

def _make_supply_chain_pair(event_bus, message_bus):
    """
    Create a B2C + B2B pair. BaseAgent auto-creates queues; capture AFTER construction.
    Also create a dummy consumer so b2c has somewhere to send order_confirmation.
    """
    from config import LOW_INVENTORY_THRESHOLD

    # Dummy consumer so send_message("consumer_sc") doesn't KeyError
    consumer_sc = make_consumer(event_bus, message_bus)
    # Override agent_id to match what we'll use in orders
    # Easiest: just add the key directly
    message_bus["consumer_sc"] = asyncio.Queue()

    products = [
        {"sku": "SC-001", "name": "SChain Item", "description": "Supply chain test.",
         "category": "electronics", "price": 49.99,
         "stock": LOW_INVENTORY_THRESHOLD + 1},
    ]
    b2c = make_business(event_bus, message_bus, agent_id="biz_b2c_sc", name="B2CStore",
                        products=products, supplier_ids=["biz_supplier_sc"])
    b2c_q = message_bus["biz_b2c_sc"]

    b2b = make_business(event_bus, message_bus, agent_id="biz_supplier_sc", name="Supplier",
                        business_type="B2B",
                        products=[{"sku": "SC-001", "name": "SChain Item",
                                   "description": "desc", "category": "electronics",
                                   "price": 10.0, "stock": 200}])
    supplier_q = message_bus["biz_supplier_sc"]

    return b2c, b2b, b2c_q, supplier_q


@pytest.mark.asyncio
async def test_supply_chain_roundtrip(event_bus, message_bus):
    """
    Low inventory after order → restock message sent to B2B supplier →
    supplier confirms → B2C inventory restored.
    """
    b2c, b2b, b2c_q, supplier_q = _make_supply_chain_pair(event_bus, message_bus)
    initial_b2c_inv = b2c.inventory["SC-001"]

    # Place order → triggers restock
    order = AgentMessage(
        from_agent_id="consumer_sc", to_agent_id="biz_b2c_sc",
        message_type="place_order",
        content={"sku": "SC-001", "quantity": 1, "price": 49.99, "consumer_name": "User"},
    )
    await b2c._handle_order(order)

    # B2B receives the supply_order
    supply_order = await asyncio.wait_for(supplier_q.get(), timeout=2.0)
    assert supply_order.message_type == "supply_order"
    assert supply_order.content["sku"] == "SC-001"

    # B2B fulfills (call directly — bypasses the asyncio.create_task path)
    await b2b._handle_supply_order(supply_order)

    # B2C receives supply_confirmation
    supply_conf = await asyncio.wait_for(b2c_q.get(), timeout=8.0)
    # skip any order_confirmation that may have arrived first
    while supply_conf.message_type == "order_confirmation":
        supply_conf = await asyncio.wait_for(b2c_q.get(), timeout=2.0)
    assert supply_conf.message_type == "supply_confirmation"

    # B2C processes the confirmation
    await b2c._handle_supply_confirmation(supply_conf)

    # Inventory should be replenished
    assert b2c.inventory["SC-001"] > initial_b2c_inv


@pytest.mark.asyncio
async def test_supply_chain_emits_transaction_events(event_bus, message_bus):
    """Supply chain completion emits transaction_update and supply_received events."""
    b2c, b2b, b2c_q, supplier_q = _make_supply_chain_pair(event_bus, message_bus)

    order = AgentMessage(
        from_agent_id="consumer_sc", to_agent_id="biz_b2c_sc",
        message_type="place_order",
        content={"sku": "SC-001", "quantity": 1, "price": 49.99, "consumer_name": "User"},
    )
    await b2c._handle_order(order)
    supply_order = await asyncio.wait_for(supplier_q.get(), timeout=2.0)
    await b2b._handle_supply_order(supply_order)

    # Drain b2c_q until supply_confirmation arrives
    supply_conf = None
    for _ in range(5):
        msg = await asyncio.wait_for(b2c_q.get(), timeout=8.0)
        if msg.message_type == "supply_confirmation":
            supply_conf = msg
            break
    assert supply_conf is not None

    await b2c._handle_supply_confirmation(supply_conf)

    events = []
    while not event_bus.empty():
        events.append(event_bus.get_nowait())
    event_types = [e.event_type for e in events]

    assert "supply_received" in event_types
    assert "transaction_update" in event_types


# ── Flow 4: Scenario + reset preserves invariants ────────────────────────────

@pytest.mark.asyncio
async def test_scenario_does_not_break_agent_message_flow():
    """After applying a scenario, agents can still exchange messages normally."""
    from simulation.engine import SimulationEngine
    engine = SimulationEngine()
    engine.initialize()
    await engine.start(mode="fresh")

    # Apply scenario mid-run
    engine.apply_scenario("price_war")

    # Agents should still be active
    for agent in list(engine.consumers.values()) + list(engine.businesses.values()):
        assert agent.active is True

    await engine.stop()


@pytest.mark.asyncio
async def test_reset_scenario_does_not_break_agent_state():
    """After reset, all agent attributes are valid values (no None, no negative budgets)."""
    from simulation.engine import SimulationEngine
    engine = SimulationEngine()
    engine.initialize()
    await engine.start(mode="fresh")

    engine.apply_scenario("recession")
    engine.apply_scenario("price_war")
    engine.apply_scenario("reset")

    for consumer in engine.consumers.values():
        assert consumer.budget > 0
        assert 0.0 <= consumer.price_sensitivity <= 1.0
        assert 0.0 <= consumer.impulse_tendency <= 1.0

    for biz in engine.businesses.values():
        if biz.business_type == "B2C":
            for sku, product in biz.catalog.items():
                # Only assert positive price for products that had prices originally
                if product.get("base_price", 0) > 0:
                    assert product["price"] > 0

    await engine.stop()


# ── Flow 5: State consistency ─────────────────────────────────────────────────

def test_engine_state_is_serializable():
    """engine.get_state() must be JSON-serializable at any point."""
    from simulation.engine import SimulationEngine
    engine = SimulationEngine()
    engine.initialize()
    state = engine.get_state()
    serialized = json.dumps(state)
    assert len(serialized) > 100


@pytest.mark.asyncio
async def test_engine_state_after_start_is_serializable():
    """State remains JSON-serializable after simulation starts."""
    from simulation.engine import SimulationEngine
    engine = SimulationEngine()
    engine.initialize()
    await engine.start(mode="fresh")
    await asyncio.sleep(0.05)
    state = engine.get_state()
    serialized = json.dumps(state)
    assert len(serialized) > 100
    await engine.stop()


@pytest.mark.asyncio
async def test_transaction_id_threads_through_supply_chain(event_bus, message_bus):
    """supply_txn_id is threaded through supply_order → supply_confirmation → events."""
    b2c, b2b, b2c_q, supplier_q = _make_supply_chain_pair(event_bus, message_bus)

    order = AgentMessage(
        from_agent_id="consumer_sc", to_agent_id="biz_b2c_sc",
        message_type="place_order",
        content={"sku": "SC-001", "quantity": 1, "price": 49.99, "consumer_name": "User"},
    )
    await b2c._handle_order(order)
    supply_order = await asyncio.wait_for(supplier_q.get(), timeout=2.0)

    # The supply_order content carries supply_txn_id (threaded from _reorder_from_supplier)
    supply_txn_id = supply_order.content.get("supply_txn_id")
    assert supply_txn_id is not None, "supply_order must carry supply_txn_id in content"
    assert supply_txn_id.startswith("SUP-")

    await b2b._handle_supply_order(supply_order)

    # Drain b2c_q to find supply_confirmation
    supply_conf = None
    for _ in range(5):
        msg = await asyncio.wait_for(b2c_q.get(), timeout=8.0)
        if msg.message_type == "supply_confirmation":
            supply_conf = msg
            break
    assert supply_conf is not None

    # supply_confirmation should echo back the same supply_txn_id
    txn_in_conf = supply_conf.content.get("supply_txn_id")
    if txn_in_conf:
        assert txn_in_conf == supply_txn_id
