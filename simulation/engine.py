from typing import Optional
import asyncio
from agents.consumer import ConsumerAgent
from agents.business import BusinessAgent
from simulation.seed_data import ALL_BUSINESSES, CONSUMERS
from simulation.events import SimEvent
from db.persistence import save_simulation, load_simulation, save_transaction
from config import DB_PATH, SIMULATION_SPEED_FACTOR


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
        self.message_log: list = []
        self._initialized = False
        self.speed_factor: float = SIMULATION_SPEED_FACTOR
        self.active_scenarios: list[str] = []
        self._scenario_originals: dict = {}

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
        self.event_history.clear()
        self.message_log.clear()
        self._initialized = False
        self.active_scenarios = []
        self._scenario_originals = {}
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

    def set_speed(self, factor: float):
        self.speed_factor = max(0.25, min(5.0, factor))
        import config
        config.SIMULATION_SPEED_FACTOR = self.speed_factor

    def apply_scenario(self, scenario_type: str) -> str:
        """Mutate live agent state to simulate market conditions."""

        if scenario_type == "reset":
            # Restore saved originals
            for consumer_id, orig in self._scenario_originals.get("consumers", {}).items():
                c = self.consumers.get(consumer_id)
                if c:
                    for k, v in orig.items():
                        setattr(c, k, v)
            for biz_id, orig in self._scenario_originals.get("businesses", {}).items():
                b = self.businesses.get(biz_id)
                if b:
                    if "inventory" in orig:
                        b.inventory = dict(orig["inventory"])
                    if "catalog_prices" in orig:
                        for sku, price in orig["catalog_prices"].items():
                            if sku in b.catalog:
                                b.catalog[sku]["price"] = price
            self.active_scenarios.clear()
            self._scenario_originals = {}
            return "Simulation reset to original values"

        # Save originals before first modification
        if not self._scenario_originals:
            self._scenario_originals["consumers"] = {
                c_id: {"budget": c.budget, "impulse_tendency": c.impulse_tendency,
                       "price_sensitivity": c.price_sensitivity}
                for c_id, c in self.consumers.items()
            }
            self._scenario_originals["businesses"] = {
                b_id: {"inventory": dict(b.inventory),
                       "catalog_prices": {sku: p["price"] for sku, p in b.catalog.items()}}
                for b_id, b in self.businesses.items()
            }

        if scenario_type == "recession":
            for c in self.consumers.values():
                c.budget = max(50, c.budget * 0.60)
                c.price_sensitivity = min(1.0, c.price_sensitivity + 0.20)
            self.active_scenarios.append("recession")
            return "📉 Recession applied: consumer budgets cut 40%, price sensitivity up"

        elif scenario_type == "black_friday":
            for c in self.consumers.values():
                c.budget = c.budget * 1.30
                c.impulse_tendency = min(1.0, c.impulse_tendency + 0.25)
            self.active_scenarios.append("black_friday")
            return "🛍️ Black Friday: budgets +30%, impulse tendency +25%"

        elif scenario_type == "supply_shock":
            for b in self.businesses.values():
                if b.business_type == "B2B":
                    for sku in b.inventory:
                        b.inventory[sku] = max(2, b.inventory[sku] // 10)
            self.active_scenarios.append("supply_shock")
            return "🏭 Supply shock: B2B supplier inventories reduced to ~10%"

        elif scenario_type == "price_war":
            for b in self.businesses.values():
                if b.business_type == "B2C":
                    for sku, product in b.catalog.items():
                        product["price"] = round(product["price"] * 0.80, 2)
            self.active_scenarios.append("price_war")
            return "💥 Price war: all B2C prices reduced 20%"

        elif scenario_type == "quality_boost":
            # Give imperfect businesses a minimal FAQ and policy boost
            for b in self.businesses.values():
                if b.business_type == "B2C" and b.quality_score < 65:
                    if not b.faqs:
                        b.faqs = [
                            {"question": "What is your return policy?", "answer": "30-day returns accepted."},
                            {"question": "How long does shipping take?", "answer": "3-5 business days."},
                        ]
                    if not b.policies.get("return_policy"):
                        b.policies["return_policy"] = "30-day returns"
                    if not b.policies.get("shipping_policy"):
                        b.policies["shipping_policy"] = "Standard 3-5 day shipping"
                    # Fix zero-priced products
                    for sku, product in b.catalog.items():
                        if product.get("price", 0) <= 0:
                            product["price"] = product.get("base_price", 25.0) or 25.0
                        if not product.get("description"):
                            product["description"] = f"Quality {product.get('name', 'product')} — see details."
                    # Recompute quality score
                    from agents.business import compute_quality_score
                    b.quality_score, b.quality_issues = compute_quality_score(
                        b.catalog, b.description, b.faqs, b.policies,
                        b.founded_year, b.employee_count, b.headquarters
                    )
            self.active_scenarios.append("quality_boost")
            return "⭐ Quality boost: imperfect merchants improved their catalogs"

        else:
            return f"Unknown scenario: {scenario_type}"

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
            "speed_factor": self.speed_factor,
            "active_scenarios": list(self.active_scenarios),
        }
