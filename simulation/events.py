from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

EVENT_COLORS = {
    "simulation_started": "#22c55e",
    "simulation_stopped": "#ef4444",
    "state_change": "#3b82f6",
    "product_query": "#8b5cf6",
    "product_query_received": "#a78bfa",
    "agent_question": "#f59e0b",
    "agent_answer": "#fbbf24",
    "purchase_completed": "#22c55e",
    "purchase_passed": "#6b7280",
    "budget_exceeded": "#f97316",
    "review_posted": "#ec4899",
    "review_received": "#f472b6",
    "order_fulfilled": "#10b981",
    "out_of_stock": "#ef4444",
    "supply_order_sent": "#f97316",
    "supply_order_fulfilled": "#84cc16",
    "supply_received": "#a3e635",
}

STATE_COLORS = {
    "idle": "#6b7280",
    "discovering": "#3b82f6",
    "considering": "#f59e0b",
    "converting": "#22c55e",
    "post_purchase": "#ec4899",
}


class SimEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_type: Optional[str] = None
    data: dict = {}
    message: str = ""
    color: str = "#6b7280"

    def model_post_init(self, __context):
        if not self.color or self.color == "#6b7280":
            self.color = EVENT_COLORS.get(self.event_type, "#6b7280")
