import asyncio
from agents.consumer import ConsumerAgent
from agents.merchant import MerchantAgent
from agents.supplier import SupplierAgent
from simulation.seed_data import MERCHANTS, SUPPLIERS, CONSUMERS
from simulation.events import SimEvent


class SimulationEngine:
    def __init__(self):
        self.event_bus: asyncio.Queue = asyncio.Queue()
        self.message_bus: dict = {}
        self.consumers: dict[str, ConsumerAgent] = {}
        self.merchants: dict[str, MerchantAgent] = {}
        self.suppliers: dict[str, SupplierAgent] = {}
        self.running = False
        self.tasks: list = []
        self.event_history: list = []
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        for s in SUPPLIERS:
            agent = SupplierAgent(
                agent_id=s["agent_id"],
                name=s["name"],
                description=s["description"],
                catalog=s["catalog"],
                event_bus=self.event_bus,
                message_bus=self.message_bus,
            )
            self.suppliers[s["agent_id"]] = agent

        for m in MERCHANTS:
            agent = MerchantAgent(
                agent_id=m["agent_id"],
                name=m["name"],
                description=m["description"],
                vertical=m["vertical"],
                products=m["products"],
                faqs=m["faqs"],
                supplier_id=m.get("supplier_id"),
                event_bus=self.event_bus,
                message_bus=self.message_bus,
            )
            self.merchants[m["agent_id"]] = agent

        for c in CONSUMERS:
            agent = ConsumerAgent(
                agent_id=c["agent_id"],
                name=c["name"],
                persona=c["persona"],
                preferences=c["preferences"],
                budget=c["budget"],
                event_bus=self.event_bus,
                message_bus=self.message_bus,
                merchant_registry=self.merchants,
            )
            self.consumers[c["agent_id"]] = agent

        self._initialized = True

    async def start(self):
        if self.running:
            return
        self.initialize()
        self.running = True

        for agent in list(self.consumers.values()) + list(self.merchants.values()) + list(self.suppliers.values()):
            agent.active = True

        self.tasks = []
        for agent in list(self.suppliers.values()) + list(self.merchants.values()) + list(self.consumers.values()):
            self.tasks.append(asyncio.create_task(agent.run()))

        await self.event_bus.put(SimEvent(
            event_type="simulation_started",
            message=f"🟢 Simulation started — {len(self.consumers)} consumers, {len(self.merchants)} merchants, {len(self.suppliers)} suppliers",
            data={
                "consumers": len(self.consumers),
                "merchants": len(self.merchants),
                "suppliers": len(self.suppliers),
            },
        ))

    async def stop(self):
        if not self.running:
            return
        self.running = False

        for agent in list(self.consumers.values()) + list(self.merchants.values()) + list(self.suppliers.values()):
            agent.active = False

        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

        await self.event_bus.put(SimEvent(
            event_type="simulation_stopped",
            message="🔴 Simulation stopped",
            data={},
        ))

    def get_state(self):
        total_revenue = sum(m.total_revenue for m in self.merchants.values())
        total_orders = sum(len(m.orders) for m in self.merchants.values())
        active_consumers = sum(1 for c in self.consumers.values() if c.state.value != "idle")

        return {
            "running": self.running,
            "consumers": [c.get_state_dict() for c in self.consumers.values()],
            "merchants": [m.get_state_dict() for m in self.merchants.values()],
            "suppliers": [s.get_state_dict() for s in self.suppliers.values()],
            "stats": {
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,
                "active_consumers": active_consumers,
                "total_events": len(self.event_history),
            },
            "recent_events": self.event_history[-50:],
        }
