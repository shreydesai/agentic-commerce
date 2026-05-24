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
    description: str = ""
    category: str = ""
    price: float = 0.0
    stock: int = 20
    variants: list[ProductVariant] = []
    tags: list[str] = []
    rating: float = 4.0
    review_count: int = 0


class FAQ(BaseModel):
    question: str
    answer: str


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent_id: str
    to_agent_id: str
    message_type: str
    content: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Transaction(BaseModel):
    transaction_id: str = Field(default_factory=lambda: f"TXN-{str(uuid.uuid4())[:6].upper()}")
    consumer_id: str
    consumer_name: str
    status: str = "discovering"  # discovering|considering|converting|completed|abandoned
    funnel_steps: list[dict] = []
    businesses_contacted: list[str] = []
    products_considered: list[dict] = []
    shortlisted: list[dict] = []
    final_product: Optional[str] = None
    final_merchant: Optional[str] = None
    total: Optional[float] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
