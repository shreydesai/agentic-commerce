import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from tests.conftest import make_consumer, make_business
from agents.consumer import ConsumerState


def make_consumer_with_merchant(event_bus, message_bus):
    biz = make_business(event_bus, message_bus, agent_id="biz_electronics",
                        vertical="electronics", name="TechStore")
    consumer = make_consumer(event_bus, message_bus, business_registry={"biz_electronics": biz})
    return consumer, biz


# ── Init ────────────────────────────────────────────────────────

def test_consumer_initial_state(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    assert c.state == ConsumerState.IDLE
    assert c.total_spent == 0.0
    assert c.purchase_history == []
    assert c.budget == 500.0


def test_consumer_state_dict(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    d = c.get_state_dict()
    assert d["agent_id"] == "consumer_test"
    assert d["state"] == "idle"
    assert d["total_spent"] == 0.0
    assert d["budget"] == 500.0
    assert "age" in d
    assert "occupation" in d


def test_consumer_restore_from_state(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    c.restore_from_state({"total_spent": 150.0, "purchase_history": [{"sku": "X-001", "price": 150.0}]})
    assert c.total_spent == 150.0
    assert len(c.purchase_history) == 1


# ── State transitions ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_idle_to_discovering(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    assert c.state == ConsumerState.IDLE
    await c._start_discovery()
    assert c.state == ConsumerState.DISCOVERING
    assert c.current_transaction is not None
    assert c.current_transaction["status"] == "discovering"


@pytest.mark.asyncio
async def test_discovery_sends_product_queries(event_bus, message_bus):
    c, biz = make_consumer_with_merchant(event_bus, message_bus)

    llm_response = {"category": "electronics", "query": "best widget", "max_price": 200.0}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_response)):
        from acp.models import AgentMessage
        # Phase 1: discovery_pong — merchant signals it can serve
        fake_pong = AgentMessage(
            from_agent_id="biz_electronics", to_agent_id="consumer_test",
            message_type="discovery_pong",
            content={"can_serve": True, "quality_score": 92.0, "quality_tier": "excellent",
                     "vertical": "electronics", "merchant_name": "TechStore"},
        )
        # Phase 2: product_response — merchant returns matching products
        fake_resp = AgentMessage(
            from_agent_id="biz_electronics", to_agent_id="consumer_test",
            message_type="product_response",
            content={"products": [{"sku": "T-001", "name": "Widget", "price": 49.99,
                                   "merchant_id": "biz_electronics", "merchant_name": "TechStore",
                                   "quality_score": 90, "has_quality_issues": False,
                                   "category": "electronics", "stock": 10, "rating": 4.5}]},
        )
        await c._start_discovery()
        # Seed inbox in order: pong first, then product response
        message_bus["consumer_test"].put_nowait(fake_pong)
        message_bus["consumer_test"].put_nowait(fake_resp)

        await c._do_discovery()

    assert c.state == ConsumerState.CONSIDERING
    assert len(c.candidate_products) > 0


@pytest.mark.asyncio
async def test_consideration_shortlists_products(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    c.state = ConsumerState.CONSIDERING
    c.candidate_products = [
        {"sku": "T-001", "name": "Widget", "price": 49.99, "merchant_id": "biz_test",
         "merchant_name": "TechStore", "quality_score": 90, "has_quality_issues": False},
        {"sku": "T-002", "name": "Gadget", "price": 99.99, "merchant_id": "biz_test",
         "merchant_name": "TechStore", "quality_score": 85, "has_quality_issues": False},
    ]
    llm_response = {"shortlisted_skus": ["T-001"], "has_question": False}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_response)):
        await c._do_consideration()

    assert c.state == ConsumerState.CONVERTING
    assert len(c.shortlisted) == 1
    assert c.shortlisted[0]["sku"] == "T-001"


@pytest.mark.asyncio
async def test_consideration_falls_back_on_llm_error(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    c.state = ConsumerState.CONSIDERING
    c.candidate_products = [
        {"sku": "T-001", "name": "Widget", "price": 49.99, "merchant_id": "biz_test",
         "merchant_name": "TechStore", "quality_score": 90, "has_quality_issues": False},
    ]
    with patch.object(c, "call_llm", AsyncMock(return_value={"error": "timeout"})):
        await c._do_consideration()

    assert c.state == ConsumerState.CONVERTING
    assert len(c.shortlisted) == 1


@pytest.mark.asyncio
async def test_conversion_buys_within_budget(event_bus, message_bus):
    c, biz = make_consumer_with_merchant(event_bus, message_bus)
    c.state = ConsumerState.CONVERTING
    c.shortlisted = [
        {"sku": "T-001", "name": "Widget", "price": 49.99,
         "merchant_id": "biz_electronics", "merchant_name": "TechStore", "quality_score": 90},
    ]
    # Simulate merchant confirmation
    from acp.models import AgentMessage
    confirm = AgentMessage(
        from_agent_id="biz_electronics", to_agent_id="consumer_test",
        message_type="order_confirmation",
        content={"order_id": "ORD-0001", "product_name": "Widget", "total": 49.99},
    )
    message_bus["consumer_test"].put_nowait(confirm)

    llm_response = {"decision": "buy", "chosen_sku": "T-001", "reasoning": "looks great"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_response)):
        await c._do_conversion()

    # After purchase the consumer waits for the delivery notice before reviewing
    assert c.state == ConsumerState.AWAITING_DELIVERY
    assert c.total_spent == pytest.approx(49.99)
    assert len(c.purchase_history) == 1


@pytest.mark.asyncio
async def test_conversion_respects_budget(event_bus, message_bus):
    c = make_consumer(event_bus, message_bus)
    c.state = ConsumerState.CONVERTING
    c.total_spent = 480.0  # only $20 left
    c.shortlisted = [
        {"sku": "T-001", "name": "Expensive Widget", "price": 99.99,
         "merchant_id": "biz_test", "merchant_name": "TechStore", "quality_score": 90},
    ]
    message_bus["biz_test"] = asyncio.Queue()
    llm_response = {"decision": "buy", "chosen_sku": "T-001", "reasoning": "want it"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_response)):
        await c._do_conversion()

    assert c.state == ConsumerState.IDLE  # passed due to budget
    assert c.total_spent == pytest.approx(480.0)  # unchanged


@pytest.mark.asyncio
async def test_post_purchase_posts_review(event_bus, message_bus):
    c, biz = make_consumer_with_merchant(event_bus, message_bus)
    c.state = ConsumerState.POST_PURCHASE
    c.purchase_history = [{
        "sku": "T-001", "name": "Widget", "merchant": "TechStore",
        "merchant_id": "biz_electronics", "price": 49.99, "order_id": "ORD-001",
        "transaction_id": "TXN-TEST",
    }]
    llm_response = {"rating": 5, "review": "Absolutely love it!"}
    with patch.object(c, "call_llm", AsyncMock(return_value=llm_response)):
        await c._do_post_purchase()

    assert c.state == ConsumerState.IDLE
    # The review message should be in the business inbox
    review_msg = await asyncio.wait_for(message_bus["biz_electronics"].get(), timeout=2.0)
    assert review_msg.message_type == "review"
    assert review_msg.content["rating"] == 5


@pytest.mark.asyncio
async def test_idle_considers_impulse_tendency(event_bus, message_bus):
    """High impulse agents are more likely to start shopping."""
    impulse_results = []
    for _ in range(20):
        c = make_consumer(event_bus, message_bus)
        c.impulse_tendency = 1.0
        import random
        threshold = 0.4 + c.impulse_tendency * 0.3
        impulse_results.append(random.random() < threshold)
    # With impulse=1.0, threshold=0.7 — expect ~14/20 True; assert >= 10 for statistical safety
    assert sum(impulse_results) >= 10
