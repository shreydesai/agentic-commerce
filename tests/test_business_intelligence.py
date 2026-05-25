"""
Tests for v0.2 business intelligence features:
  - queries_received / queries_converted / conversion_rate tracking
  - _handle_negotiation_request (LLM path + fallback path)
  - negotiation floor price clamping
  - _handle_poor_reviews emits catalog_update
  - _strategic_review appends to strategy_notes, emits strategy_update
  - get_state_dict includes intelligence metrics
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import make_business


# ── Conversion tracking ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_product_query_increments_queries_received(event_bus, message_bus, sample_products):
    """Every product_query increments queries_received."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    assert biz.queries_received == 0
    for _ in range(3):
        msg = AgentMessage(
            from_agent_id="consumer_test", to_agent_id="biz_test",
            message_type="product_query",
            content={"query": "widget", "category": "electronics", "max_price": 200.0},
        )
        await biz._handle_product_query(msg)

    assert biz.queries_received == 3


@pytest.mark.asyncio
async def test_successful_order_increments_queries_converted(event_bus, message_bus, sample_products):
    """Fulfilled order increments queries_converted."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    assert biz.queries_converted == 0
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="place_order",
        content={"sku": "TEST-001", "quantity": 1, "price": 49.99, "consumer_name": "Alice"},
    )
    await biz._handle_order(msg)
    assert biz.queries_converted == 1


@pytest.mark.asyncio
async def test_out_of_stock_order_does_not_increment_converted(event_bus, message_bus):
    """Rejected orders (out of stock) do not increment queries_converted."""
    products = [{"sku": "OOS-001", "name": "Item", "description": "desc",
                 "category": "electronics", "price": 49.99, "stock": 0}]
    biz = make_business(event_bus, message_bus, products=products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="place_order",
        content={"sku": "OOS-001", "quantity": 1, "price": 49.99, "consumer_name": "Bob"},
    )
    await biz._handle_order(msg)
    assert biz.queries_converted == 0


def test_state_dict_includes_conversion_metrics(event_bus, message_bus, sample_products):
    """get_state_dict() includes queries_received, queries_converted, conversion_rate."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    biz.queries_received = 10
    biz.queries_converted = 4
    d = biz.get_state_dict()
    assert d["queries_received"] == 10
    assert d["queries_converted"] == 4
    assert d["conversion_rate"] == pytest.approx(0.4)


def test_conversion_rate_zero_when_no_queries(event_bus, message_bus):
    """Conversion rate does not divide by zero when no queries received."""
    biz = make_business(event_bus, message_bus)
    d = biz.get_state_dict()
    assert d["conversion_rate"] == 0.0


def test_state_dict_includes_strategy_notes(event_bus, message_bus):
    """get_state_dict() includes last 3 strategy_notes."""
    biz = make_business(event_bus, message_bus)
    biz.strategy_notes = ["note1", "note2", "note3", "note4", "note5"]
    d = biz.get_state_dict()
    assert len(d["strategy_notes"]) == 3
    assert d["strategy_notes"] == ["note3", "note4", "note5"]


# ── Negotiation handling ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_negotiation_unknown_sku_sends_decline(event_bus, message_bus):
    """Negotiation for unknown SKU returns negotiation_decline immediately."""
    biz = make_business(event_bus, message_bus)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "NONEXISTENT-999", "preferred_price": 40.0,
                 "max_price": 50.0, "transaction_id": "TXN-001"},
    )
    await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "negotiation_decline"
    assert response.content.get("reason") == "product not found"


@pytest.mark.asyncio
async def test_negotiation_llm_accept_sends_counter_offer(event_bus, message_bus, sample_products):
    """When LLM returns 'accept', a counter_offer is sent to consumer."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "TEST-001", "preferred_price": 42.0, "max_price": 49.99,
                 "transaction_id": "TXN-001", "reason": "budget constrained"},
    )
    llm_resp = {"action": "accept", "offered_price": 44.0, "reason": "Happy to help"}
    with patch.object(biz, "call_llm", AsyncMock(return_value=llm_resp)):
        await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "counter_offer"
    assert response.content["offered_price"] == pytest.approx(44.0)
    assert response.content["original_price"] == pytest.approx(49.99)


@pytest.mark.asyncio
async def test_negotiation_llm_decline_sends_negotiation_decline(event_bus, message_bus, sample_products):
    """When LLM returns 'decline', a negotiation_decline is sent to consumer."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "TEST-001", "preferred_price": 20.0, "max_price": 25.0,
                 "transaction_id": "TXN-002"},
    )
    llm_resp = {"action": "decline", "offered_price": 49.99, "reason": "Price is firm"}
    with patch.object(biz, "call_llm", AsyncMock(return_value=llm_resp)):
        await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "negotiation_decline"


@pytest.mark.asyncio
async def test_negotiation_offered_price_clamped_to_floor(event_bus, message_bus, sample_products):
    """Offered price from LLM cannot go below 82% of base_price."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "TEST-001", "preferred_price": 5.0, "max_price": 10.0,
                 "transaction_id": "TXN-003"},
    )
    # LLM tries to offer ridiculously low price
    llm_resp = {"action": "accept", "offered_price": 1.0, "reason": "Big discount"}
    with patch.object(biz, "call_llm", AsyncMock(return_value=llm_resp)):
        await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "counter_offer"
    floor = round(49.99 * 0.82, 2)  # 82% of base_price
    assert response.content["offered_price"] >= floor


@pytest.mark.asyncio
async def test_negotiation_fallback_high_inventory_sends_counter(event_bus, message_bus):
    """Fallback (LLM error): high inventory + offer ≥ floor → send counter_offer."""
    products = [{"sku": "LOTS-001", "name": "Item", "description": "desc",
                 "category": "electronics", "price": 100.0, "stock": 50}]
    biz = make_business(event_bus, message_bus, products=products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "LOTS-001", "preferred_price": 85.0, "max_price": 100.0,
                 "transaction_id": "TXN-004"},
    )
    # Force LLM to fail so fallback triggers
    with patch.object(biz, "call_llm", AsyncMock(side_effect=Exception("LLM unavailable"))):
        await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "counter_offer"
    assert response.content["offered_price"] <= 100.0


@pytest.mark.asyncio
async def test_negotiation_fallback_low_inventory_sends_decline(event_bus, message_bus):
    """Fallback (LLM error): low inventory → negotiation_decline."""
    products = [{"sku": "SCARCE-001", "name": "Item", "description": "desc",
                 "category": "electronics", "price": 100.0, "stock": 3}]
    biz = make_business(event_bus, message_bus, products=products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="negotiation_request",
        content={"sku": "SCARCE-001", "preferred_price": 85.0, "max_price": 100.0,
                 "transaction_id": "TXN-005"},
    )
    with patch.object(biz, "call_llm", AsyncMock(side_effect=Exception("LLM unavailable"))):
        await biz._handle_negotiation_request(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "negotiation_decline"


# ── Poor review response ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poor_reviews_emits_catalog_update(event_bus, message_bus, sample_products):
    """_handle_poor_reviews rewrites description and emits catalog_update event."""
    biz = make_business(event_bus, message_bus, products=sample_products)

    llm_resp = {"improved_description": "Premium-grade Widget Pro, tested by 10K customers."}
    with patch.object(biz, "call_llm", AsyncMock(return_value=llm_resp)):
        await biz._handle_poor_reviews("TEST-001", 2.5)

    # Should have emitted a catalog_update event
    events = []
    while not event_bus.empty():
        events.append(event_bus.get_nowait())
    catalog_events = [e for e in events if e.event_type == "catalog_update"]
    assert len(catalog_events) >= 1


@pytest.mark.asyncio
async def test_poor_reviews_updates_description(event_bus, message_bus, sample_products):
    """_handle_poor_reviews updates the product description in the catalog."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    original_desc = biz.catalog["TEST-001"]["description"]

    new_desc = "Completely reimagined widget with 2x durability."
    with patch.object(biz, "call_llm", AsyncMock(return_value={"improved_description": new_desc})):
        await biz._handle_poor_reviews("TEST-001", 2.5)

    assert biz.catalog["TEST-001"]["description"] == new_desc


@pytest.mark.asyncio
async def test_poor_reviews_llm_error_does_not_crash(event_bus, message_bus, sample_products):
    """_handle_poor_reviews is safe when LLM returns an error."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    with patch.object(biz, "call_llm", AsyncMock(return_value={"error": "timeout"})):
        # Should not raise
        await biz._handle_poor_reviews("TEST-001", 2.0)


@pytest.mark.asyncio
async def test_poor_reviews_triggered_when_avg_below_threshold(event_bus, message_bus, sample_products):
    """_handle_review triggers _handle_poor_reviews when avg < 3.2 with ≥2 reviews."""
    biz = make_business(event_bus, message_bus, products=sample_products)
    poor_reviews_called = []

    async def mock_poor_reviews(sku, avg):
        poor_reviews_called.append((sku, avg))

    biz._handle_poor_reviews = mock_poor_reviews

    from acp.models import AgentMessage
    for rating in [2, 2]:  # avg = 2.0 < 3.2
        msg = AgentMessage(
            from_agent_id="consumer_test", to_agent_id="biz_test",
            message_type="review",
            content={"sku": "TEST-001", "rating": rating, "review": "Bad.", "consumer_name": "X"},
        )
        await biz._handle_review(msg)

    # Give the background task a chance to run
    await asyncio.sleep(0.05)
    assert len(poor_reviews_called) >= 1
    assert poor_reviews_called[-1][0] == "TEST-001"


# ── Strategic review ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_strategic_review_appends_to_strategy_notes(event_bus, message_bus):
    """_strategic_review appends LLM insight to strategy_notes."""
    biz = make_business(event_bus, message_bus)
    assert biz.strategy_notes == []

    with patch.object(biz, "call_llm", AsyncMock(return_value={"insight": "Focus on electronics."})):
        await biz._strategic_review()

    assert len(biz.strategy_notes) >= 1
    assert any("Focus on electronics" in note for note in biz.strategy_notes)


@pytest.mark.asyncio
async def test_strategic_review_emits_strategy_update_event(event_bus, message_bus):
    """_strategic_review emits a strategy_update event."""
    biz = make_business(event_bus, message_bus)

    with patch.object(biz, "call_llm", AsyncMock(return_value={"insight": "Expand assortment."})):
        await biz._strategic_review()

    events = []
    while not event_bus.empty():
        events.append(event_bus.get_nowait())
    strategy_events = [e for e in events if e.event_type == "strategy_update"]
    assert len(strategy_events) >= 1


@pytest.mark.asyncio
async def test_strategic_review_capped_at_5_notes(event_bus, message_bus):
    """strategy_notes list is capped at 5 entries."""
    biz = make_business(event_bus, message_bus)
    biz.strategy_notes = ["old1", "old2", "old3", "old4", "old5"]

    with patch.object(biz, "call_llm", AsyncMock(return_value={"insight": "New insight."})):
        await biz._strategic_review()

    assert len(biz.strategy_notes) <= 5


@pytest.mark.asyncio
async def test_strategic_review_b2b_is_skipped(event_bus, message_bus):
    """_strategic_review is only for B2C businesses; B2B should silently skip."""
    biz = make_business(event_bus, message_bus, business_type="B2B")
    call_count = []

    async def mock_llm(*args, **kwargs):
        call_count.append(1)
        return {"insight": "B2B insight"}

    with patch.object(biz, "call_llm", mock_llm):
        await biz._strategic_review()

    # B2B should not call LLM for strategic review
    assert len(call_count) == 0
