"""
Tests for v0.2 consumer intelligence features:
  - merchant_satisfaction tracking
  - trait evolution (brand_loyalty, price_sensitivity, research_depth)
  - price negotiation protocol (negotiation_request → counter_offer → accept)
  - purchase history context in state_dict
  - restore_from_state preserves merchant_satisfaction
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import make_consumer, make_business
from agents.consumer import ConsumerState


# ── Helpers ─────────────────────────────────────────────────────────────────

def _consumer_with_merchant(event_bus, message_bus, price_sensitivity=0.7, research_depth=0.6):
    biz = make_business(
        event_bus, message_bus,
        agent_id="biz_target",
        name="TargetStore",
        products=[{"sku": "NEG-001", "name": "Widget", "description": "A widget.",
                   "category": "electronics", "price": 100.00, "stock": 20}],
    )
    from tests.conftest import make_consumer as _mc
    from agents.consumer import ConsumerAgent
    c = ConsumerAgent(
        agent_id="consumer_test",
        name="Test User",
        age=30,
        gender="female",
        occupation="Engineer",
        annual_income=80_000,
        education="Bachelor's",
        location="Austin, TX",
        household_size=2,
        shopping_interests=["electronics"],
        price_sensitivity=price_sensitivity,
        brand_loyalty=0.5,
        impulse_tendency=0.5,
        research_depth=research_depth,
        preferred_channels=["online"],
        budget=500.0,
        credit_score=720,
        persona="A balanced shopper.",
        event_bus=event_bus,
        message_bus=message_bus,
        business_registry={"biz_target": biz},
    )
    message_bus["biz_target"] = asyncio.Queue()
    return c, biz


# ── merchant_satisfaction ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_purchase_updates_merchant_satisfaction(event_bus, message_bus):
    """Rating from post_purchase is stored in merchant_satisfaction."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-001",
        "transaction_id": "TXN-TEST",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 5, "review": "Loved it!"})):
        await c._do_post_purchase()

    assert "biz_target" in c.merchant_satisfaction
    assert c.merchant_satisfaction["biz_target"] == [5]


@pytest.mark.asyncio
async def test_merchant_satisfaction_caps_at_10(event_bus, message_bus):
    """Satisfaction history is capped at 10 entries per merchant."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.merchant_satisfaction["biz_target"] = [4] * 10  # already full

    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-002",
        "transaction_id": "TXN-002",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 2, "review": "Terrible."})):
        await c._do_post_purchase()

    assert len(c.merchant_satisfaction["biz_target"]) == 10
    assert c.merchant_satisfaction["biz_target"][-1] == 2  # newest appended


@pytest.mark.asyncio
async def test_merchant_satisfaction_multiple_merchants(event_bus, message_bus):
    """Ratings for different merchants are stored independently."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.merchant_satisfaction["merchant_a"] = [3, 4]
    c.merchant_satisfaction["merchant_b"] = [5]

    # New purchase from merchant_a
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "MerchantA",
        "merchant_id": "merchant_a", "price": 50.0, "order_id": "ORD-003",
        "transaction_id": "TXN-003",
    }]
    message_bus["merchant_a"] = asyncio.Queue()
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 5, "review": "Great"})):
        await c._do_post_purchase()

    assert c.merchant_satisfaction["merchant_a"] == [3, 4, 5]
    assert c.merchant_satisfaction["merchant_b"] == [5]  # unchanged


def test_state_dict_includes_merchant_satisfaction_averages(event_bus, message_bus):
    """get_state_dict() exposes per-merchant average satisfaction, rounded to 1 decimal."""
    c = make_consumer(event_bus, message_bus)
    c.merchant_satisfaction = {
        "biz_a": [5, 4, 5],   # avg = 4.666… → rounds to 4.7
        "biz_b": [2, 3],       # avg = 2.5
    }
    d = c.get_state_dict()
    ms = d.get("merchant_satisfaction", {})
    assert "biz_a" in ms
    assert ms["biz_a"] == pytest.approx(4.7)
    assert ms["biz_b"] == pytest.approx(2.5)


def test_restore_from_state_preserves_merchant_satisfaction(event_bus, message_bus):
    """restore_from_state() loads merchant_satisfaction_raw back."""
    c = make_consumer(event_bus, message_bus)
    c.restore_from_state({
        "total_spent": 200.0,
        "purchase_history": [],
        "merchant_satisfaction_raw": {"biz_a": [4, 5], "biz_b": [3]},
    })
    assert c.merchant_satisfaction == {"biz_a": [4, 5], "biz_b": [3]}


# ── Trait evolution ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_good_review_increases_brand_loyalty(event_bus, message_bus):
    """Rating ≥ 4 → brand_loyalty +0.02, price_sensitivity -0.01."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.brand_loyalty = 0.5
    c.price_sensitivity = 0.5
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-004",
        "transaction_id": "TXN-004",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 5, "review": "Amazing!"})):
        await c._do_post_purchase()

    assert c.brand_loyalty == pytest.approx(0.52)
    assert c.price_sensitivity == pytest.approx(0.49)


@pytest.mark.asyncio
async def test_bad_review_decreases_brand_loyalty(event_bus, message_bus):
    """Rating ≤ 2 → brand_loyalty -0.03, price_sensitivity +0.02, research_depth +0.02."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.brand_loyalty = 0.5
    c.price_sensitivity = 0.5
    c.research_depth = 0.5
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-005",
        "transaction_id": "TXN-005",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 1, "review": "Terrible!"})):
        await c._do_post_purchase()

    assert c.brand_loyalty == pytest.approx(0.47)
    assert c.price_sensitivity == pytest.approx(0.52)
    assert c.research_depth == pytest.approx(0.52)


@pytest.mark.asyncio
async def test_neutral_review_does_not_evolve_traits(event_bus, message_bus):
    """Rating 3 → no trait changes."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.brand_loyalty = 0.5
    c.price_sensitivity = 0.5
    c.research_depth = 0.5
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-006",
        "transaction_id": "TXN-006",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 3, "review": "It's okay."})):
        await c._do_post_purchase()

    assert c.brand_loyalty == pytest.approx(0.5)
    assert c.price_sensitivity == pytest.approx(0.5)
    assert c.research_depth == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_traits_clamped_at_1_0(event_bus, message_bus):
    """Trait evolution must not push values above 1.0."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.brand_loyalty = 0.99
    c.price_sensitivity = 0.01
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-007",
        "transaction_id": "TXN-007",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 5, "review": "Perfect!"})):
        await c._do_post_purchase()

    assert c.brand_loyalty <= 1.0
    assert c.price_sensitivity >= 0.0


@pytest.mark.asyncio
async def test_traits_clamped_at_0_0(event_bus, message_bus):
    """Trait evolution must not push values below 0.0."""
    c, biz = _consumer_with_merchant(event_bus, message_bus)
    c.brand_loyalty = 0.01
    c.price_sensitivity = 0.99
    c.research_depth = 0.99
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "NEG-001", "name": "Widget", "merchant": "TargetStore",
        "merchant_id": "biz_target", "price": 100.00, "order_id": "ORD-008",
        "transaction_id": "TXN-008",
    }]
    with patch.object(c, "call_llm", AsyncMock(return_value={"rating": 1, "review": "Awful!"})):
        await c._do_post_purchase()

    assert c.brand_loyalty >= 0.0
    assert c.price_sensitivity <= 1.0
    assert c.research_depth <= 1.0


# ── Price negotiation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_negotiation_triggered_for_price_sensitive_consumer(event_bus, message_bus):
    """Consumer with price_sensitivity > 0.52 and research_depth > 0.35 sends negotiation_request."""
    c, biz = _consumer_with_merchant(event_bus, message_bus,
                                     price_sensitivity=0.7, research_depth=0.6)
    c.state = ConsumerState.CONVERTING
    c.shortlisted = [
        {"sku": "NEG-001", "name": "Widget", "price": 100.00,
         "merchant_id": "biz_target", "merchant_name": "TargetStore", "quality_score": 90},
    ]
    c._new_transaction()  # so _txn_id() works

    # Queue counter_offer response first, then order_confirmation
    from acp.models import AgentMessage
    counter = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="counter_offer",
        content={"sku": "NEG-001", "transaction_id": None, "offered_price": 90.0,
                 "original_price": 100.0, "offer_type": "counter", "reason": "Good deal"},
    )
    confirm = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="order_confirmation",
        content={"order_id": "ORD-NEG-001", "product_name": "Widget", "total": 90.0},
    )
    message_bus["consumer_test"].put_nowait(counter)
    message_bus["consumer_test"].put_nowait(confirm)

    llm_resp = {"decision": "buy", "chosen_sku": "NEG-001", "reasoning": "great price"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_resp)):
        await c._do_conversion()

    # Consumer should have sent negotiation_request then place_order
    msgs = []
    while not message_bus["biz_target"].empty():
        msgs.append(message_bus["biz_target"].get_nowait())
    msg_types = [m.message_type for m in msgs]

    assert "negotiation_request" in msg_types
    assert "negotiation_accept" in msg_types
    assert "place_order" in msg_types
    # Order at agreed (discounted) price
    place_order_msg = next(m for m in msgs if m.message_type == "place_order")
    assert place_order_msg.content["price"] == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_negotiation_not_triggered_for_low_sensitivity(event_bus, message_bus):
    """Consumer with price_sensitivity ≤ 0.52 does NOT send negotiation_request."""
    c, biz = _consumer_with_merchant(event_bus, message_bus,
                                     price_sensitivity=0.3, research_depth=0.6)
    c.state = ConsumerState.CONVERTING
    c.shortlisted = [
        {"sku": "NEG-001", "name": "Widget", "price": 100.00,
         "merchant_id": "biz_target", "merchant_name": "TargetStore", "quality_score": 90},
    ]
    c._new_transaction()

    from acp.models import AgentMessage
    confirm = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="order_confirmation",
        content={"order_id": "ORD-DIRECT", "product_name": "Widget", "total": 100.0},
    )
    message_bus["consumer_test"].put_nowait(confirm)

    llm_resp = {"decision": "buy", "chosen_sku": "NEG-001", "reasoning": "looks good"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_resp)):
        await c._do_conversion()

    msgs = []
    while not message_bus["biz_target"].empty():
        msgs.append(message_bus["biz_target"].get_nowait())
    msg_types = [m.message_type for m in msgs]

    assert "negotiation_request" not in msg_types
    assert "place_order" in msg_types
    place_order_msg = next(m for m in msgs if m.message_type == "place_order")
    assert place_order_msg.content["price"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_negotiation_decline_proceeds_at_full_price(event_bus, message_bus):
    """If merchant declines, consumer proceeds at full price."""
    c, biz = _consumer_with_merchant(event_bus, message_bus,
                                     price_sensitivity=0.7, research_depth=0.6)
    c.state = ConsumerState.CONVERTING
    c.shortlisted = [
        {"sku": "NEG-001", "name": "Widget", "price": 100.00,
         "merchant_id": "biz_target", "merchant_name": "TargetStore", "quality_score": 90},
    ]
    c._new_transaction()

    from acp.models import AgentMessage
    decline = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="negotiation_decline",
        content={"sku": "NEG-001", "reason": "Price is firm"},
    )
    confirm = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="order_confirmation",
        content={"order_id": "ORD-FULL", "product_name": "Widget", "total": 100.0},
    )
    message_bus["consumer_test"].put_nowait(decline)
    message_bus["consumer_test"].put_nowait(confirm)

    llm_resp = {"decision": "buy", "chosen_sku": "NEG-001", "reasoning": "still want it"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_resp)):
        await c._do_conversion()

    msgs = []
    while not message_bus["biz_target"].empty():
        msgs.append(message_bus["biz_target"].get_nowait())
    place_order_msg = next((m for m in msgs if m.message_type == "place_order"), None)
    assert place_order_msg is not None
    assert place_order_msg.content["price"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_counter_offer_above_asking_price_rejected(event_bus, message_bus):
    """If counter_offer is higher than listed price, consumer ignores it and pays full."""
    c, biz = _consumer_with_merchant(event_bus, message_bus,
                                     price_sensitivity=0.7, research_depth=0.6)
    c.state = ConsumerState.CONVERTING
    c.shortlisted = [
        {"sku": "NEG-001", "name": "Widget", "price": 100.00,
         "merchant_id": "biz_target", "merchant_name": "TargetStore", "quality_score": 90},
    ]
    c._new_transaction()

    from acp.models import AgentMessage
    bad_counter = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="counter_offer",
        content={"sku": "NEG-001", "offered_price": 120.0,  # higher than asking!
                 "original_price": 100.0, "offer_type": "counter", "reason": "Premium rate"},
    )
    confirm = AgentMessage(
        from_agent_id="biz_target", to_agent_id="consumer_test",
        message_type="order_confirmation",
        content={"order_id": "ORD-STILL-FULL", "product_name": "Widget", "total": 100.0},
    )
    message_bus["consumer_test"].put_nowait(bad_counter)
    message_bus["consumer_test"].put_nowait(confirm)

    llm_resp = {"decision": "buy", "chosen_sku": "NEG-001", "reasoning": "need it anyway"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_resp)):
        await c._do_conversion()

    msgs = []
    while not message_bus["biz_target"].empty():
        msgs.append(message_bus["biz_target"].get_nowait())
    place_order_msg = next((m for m in msgs if m.message_type == "place_order"), None)
    # Should NOT have sent negotiation_accept (counter was worse)
    assert "negotiation_accept" not in [m.message_type for m in msgs]
    assert place_order_msg is not None
    assert place_order_msg.content["price"] == pytest.approx(100.0)
