import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import make_business


# ── Quality score ───────────────────────────────────────────────

def test_quality_score_perfect(event_bus, message_bus, sample_products, sample_faqs, sample_policies):
    biz = make_business(event_bus, message_bus, products=sample_products, faqs=sample_faqs, policies=sample_policies)
    assert biz.quality_score >= 85
    assert len(biz.quality_issues) == 0


def test_quality_score_missing_prices(event_bus, message_bus, sample_faqs, sample_policies):
    products = [
        {"sku": "X-001", "name": "Widget", "description": "A widget.", "category": "electronics", "price": 0.0, "stock": 10},
        {"sku": "X-002", "name": "Gadget", "description": "A gadget.", "category": "electronics", "price": 0.0, "stock": 10},
    ]
    biz = make_business(event_bus, message_bus, products=products, faqs=sample_faqs, policies=sample_policies)
    assert biz.quality_score < 85
    assert any("price" in issue.lower() for issue in biz.quality_issues)


def test_quality_score_no_faqs(event_bus, message_bus, sample_products, sample_policies):
    biz = make_business(event_bus, message_bus, products=sample_products, faqs=[], policies=sample_policies)
    assert biz.quality_score < 95
    assert any("FAQ" in issue for issue in biz.quality_issues)


def test_quality_score_no_policies(event_bus, message_bus, sample_products, sample_faqs):
    biz = make_business(event_bus, message_bus, products=sample_products, faqs=sample_faqs, policies={})
    assert biz.quality_score < 95
    assert any("policy" in issue.lower() for issue in biz.quality_issues)


def test_quality_score_missing_company_info(event_bus, message_bus, sample_products, sample_faqs, sample_policies):
    biz = make_business(
        event_bus, message_bus,
        products=sample_products, faqs=sample_faqs, policies=sample_policies,
        founded_year=None, employee_count=None, headquarters=None,
    )
    assert biz.quality_score < 100


def test_quality_score_clamped_to_zero(event_bus, message_bus):
    products = [{"sku": f"X-{i}", "name": "", "description": "", "category": "", "price": 0.0, "stock": 0} for i in range(5)]
    biz = make_business(event_bus, message_bus, products=products, faqs=[], policies={},
                        description="", founded_year=None, employee_count=None, headquarters=None)
    assert biz.quality_score >= 0


# ── Catalog search ──────────────────────────────────────────────

def test_catalog_search_by_vertical(event_bus, message_bus, sample_products):
    biz = make_business(event_bus, message_bus, products=sample_products, vertical="electronics")
    results = biz.search_catalog("widget", "electronics", 200.0)
    assert len(results) > 0
    assert all(r["merchant_id"] == "biz_test" for r in results)


def test_catalog_search_price_filter(event_bus, message_bus, sample_products):
    biz = make_business(event_bus, message_bus, products=sample_products)
    results = biz.search_catalog("widget", "electronics", 50.0)
    assert all(r["price"] <= 50.0 for r in results)


def test_catalog_search_excludes_zero_price(event_bus, message_bus):
    products = [
        {"sku": "Z-001", "name": "NoPriceItem", "description": "No price set.", "category": "electronics", "price": 0.0, "stock": 10},
        {"sku": "Z-002", "name": "PricedItem", "description": "Has price.", "category": "electronics", "price": 29.99, "stock": 10},
    ]
    biz = make_business(event_bus, message_bus, products=products)
    results = biz.search_catalog("item", "electronics", 500.0)
    skus = [r["sku"] for r in results]
    assert "Z-001" not in skus
    assert "Z-002" in skus


def test_catalog_search_excludes_out_of_stock(event_bus, message_bus):
    products = [
        {"sku": "S-001", "name": "Sold Out", "description": "No stock.", "category": "electronics", "price": 29.99, "stock": 0},
        {"sku": "S-002", "name": "In Stock", "description": "Has stock.", "category": "electronics", "price": 29.99, "stock": 5},
    ]
    biz = make_business(event_bus, message_bus, products=products)
    results = biz.search_catalog("stock", "electronics", 500.0)
    skus = [r["sku"] for r in results]
    assert "S-001" not in skus
    assert "S-002" in skus


def test_catalog_search_returns_max_3(event_bus, message_bus):
    products = [
        {"sku": f"M-{i}", "name": f"Widget {i}", "description": "A widget.", "category": "electronics", "price": 20.0, "stock": 10}
        for i in range(6)
    ]
    biz = make_business(event_bus, message_bus, products=products)
    results = biz.search_catalog("widget", "electronics", 500.0)
    assert len(results) <= 3


# ── Message handling ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_product_query(event_bus, message_bus, sample_products):
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test",
        to_agent_id="biz_test",
        message_type="product_query",
        content={"query": "widget", "category": "electronics", "max_price": 200.0},
    )
    await biz._handle_product_query(msg)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "product_response"
    assert isinstance(response.content.get("products"), list)


@pytest.mark.asyncio
async def test_handle_order_fulfillment(event_bus, message_bus, sample_products):
    biz = make_business(event_bus, message_bus, products=sample_products)
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test",
        to_agent_id="biz_test",
        message_type="place_order",
        content={"sku": "TEST-001", "quantity": 1, "price": 49.99, "consumer_name": "Alice"},
    )
    initial_stock = biz.inventory["TEST-001"]
    await biz._handle_order(msg)

    assert biz.inventory["TEST-001"] == initial_stock - 1
    assert len(biz.orders) == 1
    assert biz.total_revenue == pytest.approx(49.99)

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "order_confirmation"
    assert response.content.get("order_id") is not None


@pytest.mark.asyncio
async def test_handle_order_out_of_stock(event_bus, message_bus, sample_products):
    products = [{"sku": "OOS-001", "name": "Widget", "description": "A widget.", "category": "electronics", "price": 49.99, "stock": 0}]
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
    assert len(biz.orders) == 0

    response = await asyncio.wait_for(consumer_q.get(), timeout=2.0)
    assert response.message_type == "order_rejected"


@pytest.mark.asyncio
async def test_handle_review_updates_rating(event_bus, message_bus, sample_products):
    biz = make_business(event_bus, message_bus, products=sample_products)
    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="review",
        content={"sku": "TEST-001", "rating": 5, "review": "Great!", "consumer_name": "Alice"},
    )
    await biz._handle_review(msg)
    assert biz.catalog["TEST-001"]["rating"] == 5.0
    assert biz.catalog["TEST-001"]["review_count"] == 1

    msg2 = AgentMessage(
        from_agent_id="consumer_test2", to_agent_id="biz_test",
        message_type="review",
        content={"sku": "TEST-001", "rating": 3, "review": "OK.", "consumer_name": "Bob"},
    )
    await biz._handle_review(msg2)
    assert biz.catalog["TEST-001"]["rating"] == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_low_inventory_triggers_reorder(event_bus, message_bus):
    from config import LOW_INVENTORY_THRESHOLD
    supplier_q = asyncio.Queue()
    message_bus["biz_supplier"] = supplier_q

    products = [{"sku": "LOW-001", "name": "Widget", "description": "A widget.", "category": "electronics",
                 "price": 49.99, "stock": LOW_INVENTORY_THRESHOLD + 1}]
    biz = make_business(event_bus, message_bus, products=products, supplier_ids=["biz_supplier"])
    consumer_q = asyncio.Queue()
    message_bus["consumer_test"] = consumer_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="consumer_test", to_agent_id="biz_test",
        message_type="place_order",
        content={"sku": "LOW-001", "quantity": 1, "price": 49.99, "consumer_name": "Alice"},
    )
    await biz._handle_order(msg)

    # Should have placed a supply order since inventory <= threshold
    supply_msg = await asyncio.wait_for(supplier_q.get(), timeout=2.0)
    assert supply_msg.message_type == "supply_order"
    assert supply_msg.content["sku"] == "LOW-001"


@pytest.mark.asyncio
async def test_b2b_supply_order_handled(event_bus, message_bus):
    biz = make_business(event_bus, message_bus, business_type="B2B")
    requester_q = asyncio.Queue()
    message_bus["biz_requester"] = requester_q

    from acp.models import AgentMessage
    msg = AgentMessage(
        from_agent_id="biz_requester", to_agent_id="biz_test",
        message_type="supply_order",
        content={"sku": "T-001", "quantity": 20, "product_name": "Widget", "merchant_name": "TechStore"},
    )
    # Run supply handler directly (it creates a task internally, so test the handler)
    await biz._handle_supply_order(msg)

    response = await asyncio.wait_for(requester_q.get(), timeout=8.0)
    assert response.message_type == "supply_confirmation"
    assert response.content["quantity"] == 20
