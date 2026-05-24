from typing import Optional
import asyncio
from agents.consumer import ConsumerAgent
from agents.business import BusinessAgent
from simulation.seed_data import ALL_BUSINESSES, CONSUMERS
from simulation.events import SimEvent
from db.persistence import save_simulation, load_simulation, save_transaction
from config import DB_PATH


class SimulationEngine:
    def __init__(self):
        self.event_bus: asyncio.Queue = asyncio.Queue()
        self.message_bus: dict = {}
        self.consumers: dict[str, ConsumerAgent] = {}
        self.businesses: dict[str, BusinessAgent] = {}
        self.transactions: dict[str, dict] = {}
        self.running = False
        self.tasks: list = []
        self.event_history: list = []
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        self._build_agents()
        self._initialized = True

    def _build_agents(self, saved_state: Optional[dict] = None):
        saved_biz = {}
        saved_con = {}
        if saved_state:
            saved_biz = {b["agent_id"]: b for b in saved_state.get("businesses", [])}
            saved_con = {c["agent_id"]: c for c in saved_state.get("consumers", [])}

        for b in ALL_BUSINESSES:
            agent = BusinessAgent(
                agent_id=b["agent_id"],
                name=b["name"],
                description=b["description"],
                vertical=b["vertical"],
                business_type=b["business_type"],
                products=b["products"],
                faqs=b.get("faqs", []),
                policies=b.get("policies", {}),
                founded_year=b.get("founded_year"),
                employee_count=b.get("employee_count"),
                annual_revenue=b.get("annual_revenue"),
                headquarters=b.get("headquarters"),
                tagline=b.get("tagline", ""),
                supplier_ids=b.get("supplier_ids", []),
                minimum_order_qty=b.get("minimum_order_qty", 1),
                wholesale_discount=b.get("wholesale_discount", 0.0),
                client_b2c_ids=b.get("client_b2c_ids", []),
                event_bus=self.event_bus,
                message_bus=self.message_bus,
            )
            if b["agent_id"] in saved_biz:
                agent.restore_from_state(saved_biz[b["agent_id"]])
            self.businesses[b["agent_id"]] = agent

        for c in CONSUMERS:
            agent = ConsumerAgent(
                agent_id=c["agent_id"],
                name=c["name"],
                age=c["age"],
                gender=c["gender"],
                occupation=c["occupation"],
                annual_income=c["annual_income"],
                education=c["education"],
                location=c["location"],
                household_size=c["household_size"],
                shopping_interests=c["shopping_interests"],
                price_sensitivity=c["price_sensitivity"],
                brand_loyalty=c["brand_loyalty"],
                impulse_tendency=c["impulse_tendency"],
                research_depth=c["research_depth"],
                preferred_channels=c["preferred_channels"],
                budget=c["budget"],
                credit_score=c["credit_score"],
                persona=c["persona"],
                event_bus=self.event_bus,
                message_bus=self.message_bus,
                business_registry=self.businesses,
            )
            if c["agent_id"] in saved_con:
                agent.restore_from_state(saved_con[c["agent_id"]])
            self.consumers[c["agent_id"]] = agent

    def reset(self, saved_state: Optional[dict] = None):
        self.consumers.clear()
        self.businesses.clear()
        self.message_bus.clear()
        self.transactions.clear()
        self._initialized = False
        self._build_agents(saved_state)
        self._initialized = True

    async def start(self, mode: str = "fresh"):
        if self.running:
            return
        if mode == "load":
            saved = load_simulation(DB_PATH)
            if saved:
                self.reset(saved_state=saved)
            else:
                self.initialize()
        else:
            self.initialize()

        self.running = True
        for agent in list(self.consumers.values()) + list(self.businesses.values()):
            agent.active = True

        self.tasks = []
        for agent in list(self.businesses.values()) + list(self.consumers.values()):
            self.tasks.append(asyncio.create_task(agent.run()))

        b2c_count = sum(1 for b in self.businesses.values() if b.business_type == "B2C")
        b2b_count = sum(1 for b in self.businesses.values() if b.business_type == "B2B")
        await self.event_bus.put(SimEvent(
            event_type="simulation_started",
            message=(
                f"🟢 Simulation started — {len(self.consumers)} consumers, "
                f"{b2c_count} B2C businesses, {b2b_count} B2B suppliers"
            ),
            data={"consumers": len(self.consumers), "b2c": b2c_count, "b2b": b2b_count},
        ))

    async def stop(self):
        if not self.running:
            return
        self.running = False
        for agent in list(self.consumers.values()) + list(self.businesses.values()):
            agent.active = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        save_simulation(self.get_state(), DB_PATH)
        await self.event_bus.put(SimEvent(
            event_type="simulation_stopped",
            message="🔴 Simulation stopped — state saved",
            data={},
        ))

    def record_transaction(self, txn: dict):
        tid = txn.get("transaction_id")
        if tid:
            self.transactions[tid] = txn
            try:
                save_transaction(txn, DB_PATH)
            except Exception:
                pass

    def get_state(self) -> dict:
        b2c = [b for b in self.businesses.values() if b.business_type == "B2C"]
        b2b = [b for b in self.businesses.values() if b.business_type == "B2B"]
        total_revenue = sum(b.total_revenue for b in b2c)
        total_orders = sum(len(b.orders) for b in b2c)
        active_consumers = sum(1 for c in self.consumers.values() if c.state.value != "idle")
        active_transactions = sum(
            1 for t in self.transactions.values()
            if t.get("status") in ("discovering", "considering", "converting")
        )
        return {
            "running": self.running,
            "consumers": [c.get_state_dict() for c in self.consumers.values()],
            "businesses": [b.get_state_dict() for b in self.businesses.values()],
            "stats": {
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,
                "active_consumers": active_consumers,
                "active_transactions": active_transactions,
                "total_events": len(self.event_history),
            },
            "transactions": list(self.transactions.values()),
            "recent_events": self.event_history[-50:],
        }
