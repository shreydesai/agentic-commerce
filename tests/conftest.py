import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def fast_asyncio_sleep(monkeypatch):
    """
    Replace asyncio.sleep with an instant yield in every test.

    Agent code uses asyncio.sleep for two purposes:
      1. Simulation realism (consumer tick pacing, supplier delay, discovery wait)
      2. Letting other coroutines run (cooperative multitasking)

    In tests we only need (2). asyncio.sleep(0) satisfies that — it yields
    control to the event loop without actually waiting — so tests that call
    _do_discovery(), _handle_supply_order(), etc. finish in milliseconds
    instead of 2-5 seconds each.

    API tests that use `started_client` still rely on time.sleep() for their
    own polling waits, which are unaffected by this patch.
    """
    async def _yield(delay=0, *args, **kwargs):
        await asyncio.sleep.__wrapped__(0)   # yield without blocking

    # Wrap asyncio.sleep so we can call the real sleep(0) inside the mock
    import asyncio as _asyncio
    _real_sleep = _asyncio.sleep
    _yield.__wrapped__ = _real_sleep

    monkeypatch.setattr(_asyncio, "sleep", _yield)


@pytest.fixture
def event_bus():
    return asyncio.Queue()


@pytest.fixture
def message_bus():
    return {}


@pytest.fixture
def mock_llm_response():
    """Factory: returns an AsyncMock that yields a given JSON dict."""
    def _make(response_dict: dict):
        import json
        mock = AsyncMock(return_value=response_dict)
        return mock
    return _make


@pytest.fixture
def sample_products():
    return [
        {"sku": "TEST-001", "name": "Widget Pro", "description": "A great widget for testing.", "category": "electronics", "price": 49.99, "stock": 20},
        {"sku": "TEST-002", "name": "Gadget Plus", "description": "An excellent gadget.", "category": "electronics", "price": 99.99, "stock": 5},
        {"sku": "TEST-003", "name": "Doohickey", "description": "A useful doohickey.", "category": "accessories", "price": 19.99, "stock": 50},
    ]


@pytest.fixture
def sample_faqs():
    return [
        {"question": "What is the return policy?", "answer": "30-day returns."},
        {"question": "Do you offer warranty?", "answer": "1-year warranty included."},
    ]


@pytest.fixture
def sample_policies():
    return {
        "return_policy": "30-day hassle-free returns",
        "shipping_policy": "Free shipping over $50",
    }


def make_business(event_bus, message_bus, products=None, faqs=None, policies=None,
                  agent_id="biz_test", name="Test Business", business_type="B2C",
                  vertical="electronics", description="A test business with good data.",
                  founded_year=2015, employee_count=100, headquarters="Austin, TX",
                  supplier_ids=None):
    from agents.business import BusinessAgent
    return BusinessAgent(
        agent_id=agent_id,
        name=name,
        description=description,
        vertical=vertical,
        business_type=business_type,
        products=products if products is not None else [
            {"sku": "T-001", "name": "Widget", "description": "A widget.", "category": vertical, "price": 49.99, "stock": 20},
            {"sku": "T-002", "name": "Gadget", "description": "A gadget.", "category": vertical, "price": 99.99, "stock": 5},
        ],
        faqs=faqs if faqs is not None else [
            {"question": "Return policy?", "answer": "30 days."},
            {"question": "Warranty?", "answer": "1 year."},
        ],
        policies=policies if policies is not None else {"return_policy": "30-day returns", "shipping_policy": "Free over $50"},
        founded_year=founded_year,
        employee_count=employee_count,
        headquarters=headquarters,
        supplier_ids=supplier_ids or [],
        event_bus=event_bus,
        message_bus=message_bus,
    )


def make_consumer(event_bus, message_bus, business_registry=None):
    from agents.consumer import ConsumerAgent
    return ConsumerAgent(
        agent_id="consumer_test",
        name="Test User",
        age=30,
        gender="female",
        occupation="Engineer",
        annual_income=100_000,
        education="Bachelor's",
        location="Austin, TX",
        household_size=2,
        shopping_interests=["electronics"],
        price_sensitivity=0.5,
        brand_loyalty=0.5,
        impulse_tendency=0.5,
        research_depth=0.5,
        preferred_channels=["online"],
        budget=500.0,
        credit_score=720,
        persona="A balanced shopper who values quality and price.",
        event_bus=event_bus,
        message_bus=message_bus,
        business_registry=business_registry or {},
    )
