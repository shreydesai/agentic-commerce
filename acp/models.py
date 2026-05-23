from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class ProductVariant(BaseModel):
    variant_id: str
    name: str
    price: float
    stock: int


class Product(BaseModel):
    sku: str
    name: str
    description: str
    category: str
    price: float
    stock: int = 20
    variants: list[ProductVariant] = []
    tags: list[str] = []
    rating: float = 4.0
    review_count: int = 0


class FAQ(BaseModel):
    question: str
    answer: str


class MerchantProfile(BaseModel):
    merchant_id: str
    business_name: str
    description: str
    vertical: str
    catalog: list[Product]
    faqs: list[FAQ]
    policies: dict = {}


class OrderItem(BaseModel):
    sku: str
    variant_id: Optional[str] = None
    quantity: int
    unit_price: float


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: f"ORD-{str(uuid.uuid4())[:6].upper()}")
    consumer_id: str
    merchant_id: str
    items: list[OrderItem]
    total: float
    status: str = "confirmed"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent_id: str
    to_agent_id: str
    message_type: str
    content: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
