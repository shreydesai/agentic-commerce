import asyncio
import random
from agents.base import BaseAgent


class SupplierAgent(BaseAgent):
    def __init__(self, agent_id, name, description, catalog, event_bus, message_bus):
        super().__init__(agent_id, name, "supplier", event_bus, message_bus)
        self.description = description
        self.catalog = {p["sku"]: dict(p) for p in catalog}
        self.orders_fulfilled = 0
        self.clients = []

    def get_state_dict(self):
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "orders_fulfilled": self.orders_fulfilled,
            "clients": self.clients,
        }

    async def run(self):
        await asyncio.sleep(random.uniform(0, 1))
        while self.active:
            await self._process_messages()
            await asyncio.sleep(1.5)

    async def _process_messages(self):
        while not self.message_bus[self.agent_id].empty():
            msg = await self.receive_message(timeout=0.1)
            if msg is None:
                break
            try:
                if msg.message_type == "supply_order":
                    asyncio.create_task(self._handle_supply_order(msg))
            except Exception as e:
                print(f"[{self.name}] error: {e}")

    async def _handle_supply_order(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 0)
        product_name = msg.content.get("product_name", sku)
        merchant_name = msg.content.get("merchant_name", "Merchant")

        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": quantity, "from": merchant_name},
            f"🏭 {self.name} received order from {merchant_name}: {quantity}x {product_name}",
        )

        # Simulate supply chain delay
        await asyncio.sleep(random.uniform(2, 5))

        self.orders_fulfilled += 1
        if merchant_name not in self.clients:
            self.clients.append(merchant_name)

        await self.send_message(msg.from_agent_id, "supply_confirmation", {
            "sku": sku,
            "quantity": quantity,
            "supplier_name": self.name,
            "delivery_days": random.randint(1, 3),
        })

        await self.emit_event(
            "supply_order_fulfilled",
            {"sku": sku, "quantity": quantity, "to": merchant_name},
            f"🚚 {self.name} shipped {quantity}x {product_name} → {merchant_name}",
        )
