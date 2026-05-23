import asyncio
import random
from agents.base import BaseAgent
from config import LOW_INVENTORY_THRESHOLD


class MerchantAgent(BaseAgent):
    def __init__(self, agent_id, name, description, vertical, products, faqs, supplier_id, event_bus, message_bus):
        super().__init__(agent_id, name, "merchant", event_bus, message_bus)
        self.description = description
        self.vertical = vertical
        self.catalog = {p["sku"]: dict(p) for p in products}
        self.inventory = {p["sku"]: p.get("stock", 20) for p in products}
        self.faqs = faqs
        self.supplier_id = supplier_id
        self.total_revenue = 0.0
        self.orders = []
        self.ratings = {}

    def get_state_dict(self):
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "vertical": self.vertical,
            "description": self.description,
            "total_revenue": round(self.total_revenue, 2),
            "order_count": len(self.orders),
            "inventory": dict(self.inventory),
            "catalog": {sku: {"name": p["name"], "price": p["price"], "rating": p.get("rating", 4.0)} for sku, p in self.catalog.items()},
        }

    def search_catalog(self, query: str, category: str, max_price: float) -> list:
        results = []
        query_words = query.lower().split()
        for sku, product in self.catalog.items():
            if self.inventory.get(sku, 0) <= 0:
                continue
            price = product.get("price", 0)
            if price > max_price:
                continue
            name_l = product.get("name", "").lower()
            desc_l = product.get("description", "").lower()
            cat_l = product.get("category", "").lower()
            match = (
                category.lower() in cat_l
                or self.vertical.lower() == category.lower()
                or any(w in name_l or w in desc_l or w in cat_l for w in query_words)
            )
            if match:
                results.append({
                    "sku": sku,
                    "name": product["name"],
                    "description": product.get("description", ""),
                    "price": price,
                    "category": product.get("category", ""),
                    "merchant_id": self.agent_id,
                    "merchant_name": self.name,
                    "stock": self.inventory.get(sku, 0),
                    "rating": product.get("rating", 4.0),
                })
        return results[:3]

    async def run(self):
        await asyncio.sleep(random.uniform(0, 2))
        while self.active:
            await self._process_messages()
            await asyncio.sleep(1.5)

    async def _process_messages(self):
        while not self.message_bus[self.agent_id].empty():
            msg = await self.receive_message(timeout=0.1)
            if msg is None:
                break
            try:
                await self._handle_message(msg)
            except Exception as e:
                print(f"[{self.name}] message error: {e}")

    async def _handle_message(self, msg):
        if msg.message_type == "product_query":
            await self._handle_product_query(msg)
        elif msg.message_type == "question":
            await self._handle_question(msg)
        elif msg.message_type == "place_order":
            await self._handle_order(msg)
        elif msg.message_type == "review":
            await self._handle_review(msg)
        elif msg.message_type == "supply_confirmation":
            await self._handle_supply_confirmation(msg)

    async def _handle_product_query(self, msg):
        query = msg.content.get("query", "")
        category = msg.content.get("category", "")
        max_price = msg.content.get("max_price", 9999)
        products = self.search_catalog(query, category, max_price)
        await self.send_message(msg.from_agent_id, "product_response", {
            "products": products,
            "merchant_name": self.name,
        })
        if products:
            await self.emit_event(
                "product_query_received",
                {"query": query, "results": len(products)},
                f"{self.name} returned {len(products)} result(s) for \"{query}\"",
            )

    async def _handle_question(self, msg):
        question = msg.content.get("question", "")
        sku = msg.content.get("sku", "")
        product = self.catalog.get(sku, {})
        faq_text = " | ".join(f"Q:{f['question']} A:{f['answer']}" for f in self.faqs[:3])
        result = await self.call_llm(
            system=f"You are {self.name}, a {self.vertical} retailer. Be helpful, brief. Return ONLY valid JSON.",
            user=f"Customer asks about {product.get('name', sku)}: \"{question}\"\nFAQs: {faq_text}\nReturn: {{\"answer\": \"concise answer\"}}",
        )
        answer = result.get("answer", "Please contact our support team for more details.")
        await self.send_message(msg.from_agent_id, "question_answer", {
            "answer": answer,
            "merchant_name": self.name,
        })

    async def _handle_order(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 1)
        price = msg.content.get("price", 0)
        consumer_name = msg.content.get("consumer_name", "Customer")

        if self.inventory.get(sku, 0) >= quantity:
            self.inventory[sku] -= quantity
            self.total_revenue += price * quantity
            order = {
                "order_id": f"ORD-{len(self.orders)+1:04d}",
                "consumer_id": msg.from_agent_id,
                "consumer_name": consumer_name,
                "sku": sku,
                "product_name": self.catalog.get(sku, {}).get("name", sku),
                "quantity": quantity,
                "total": price * quantity,
            }
            self.orders.append(order)
            await self.send_message(msg.from_agent_id, "order_confirmation", order)
            await self.emit_event(
                "order_fulfilled",
                {"order": order, "inventory_left": self.inventory[sku]},
                f"📦 {self.name} fulfilled order for {consumer_name}: {self.catalog.get(sku,{}).get('name',sku)} (${price:.2f})",
            )
            if self.inventory[sku] <= LOW_INVENTORY_THRESHOLD and self.supplier_id:
                await self._reorder_from_supplier(sku)
        else:
            await self.send_message(msg.from_agent_id, "order_rejected", {"reason": "out of stock", "sku": sku})
            await self.emit_event(
                "out_of_stock",
                {"sku": sku, "product": self.catalog.get(sku, {}).get("name", sku)},
                f"⚠️ {self.name} is out of stock: {self.catalog.get(sku,{}).get('name',sku)}",
            )

    async def _reorder_from_supplier(self, sku):
        restock_qty = 25
        await self.send_message(self.supplier_id, "supply_order", {
            "sku": sku,
            "product_name": self.catalog.get(sku, {}).get("name", sku),
            "quantity": restock_qty,
            "merchant_name": self.name,
        })
        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": restock_qty},
            f"🔄 {self.name} ordered {restock_qty}x {self.catalog.get(sku,{}).get('name',sku)} from supplier",
        )

    async def _handle_review(self, msg):
        sku = msg.content.get("sku")
        rating = msg.content.get("rating", 4)
        consumer_name = msg.content.get("consumer_name", "Customer")
        if sku not in self.ratings:
            self.ratings[sku] = []
        self.ratings[sku].append(rating)
        if sku in self.catalog:
            avg = sum(self.ratings[sku]) / len(self.ratings[sku])
            self.catalog[sku]["rating"] = round(avg, 1)
            self.catalog[sku]["review_count"] = len(self.ratings[sku])
        await self.emit_event(
            "review_received",
            {"sku": sku, "rating": rating, "from": consumer_name},
            f"⭐ {self.name} received {rating}/5 review from {consumer_name}",
        )

    async def _handle_supply_confirmation(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 0)
        supplier_name = msg.content.get("supplier_name", "Supplier")
        if sku in self.inventory:
            self.inventory[sku] += quantity
        await self.emit_event(
            "supply_received",
            {"sku": sku, "quantity": quantity, "supplier": supplier_name},
            f"✅ {self.name} received {quantity}x restock from {supplier_name}",
        )
