import pytest
from acp.models import Product, AgentMessage, Transaction


def test_product_defaults():
    p = Product(sku="P-001", name="Widget")
    assert p.price == 0.0
    assert p.stock == 20
    assert p.rating == 4.0
    assert p.review_count == 0
    assert p.variants == []


def test_product_full():
    p = Product(sku="P-002", name="Pro Widget", description="Best widget.", category="electronics", price=49.99, stock=10)
    assert p.sku == "P-002"
    assert p.price == 49.99
    assert p.stock == 10


def test_agent_message_auto_id():
    m = AgentMessage(from_agent_id="a", to_agent_id="b", message_type="query", content={"q": "test"})
    assert len(m.message_id) == 8
    assert m.from_agent_id == "a"
    assert m.to_agent_id == "b"


def test_transaction_defaults():
    t = Transaction(consumer_id="c1", consumer_name="Alice")
    assert t.status == "discovering"
    assert t.funnel_steps == []
    assert t.businesses_contacted == []
    assert t.total is None
    assert t.transaction_id.startswith("TXN-")


def test_transaction_completion():
    t = Transaction(consumer_id="c1", consumer_name="Alice")
    t.status = "completed"
    t.final_product = "Widget Pro"
    t.final_merchant = "TechZone"
    t.total = 49.99
    assert t.status == "completed"
    assert t.total == 49.99
