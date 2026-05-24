from typing import Optional
import asyncio
import random
from agents.base import BaseAgent
from config import LOW_INVENTORY_THRESHOLD


def compute_quality_score(catalog: dict, description: str, faqs: list, policies: dict,
                           founded_year, employee_count, headquarters) -> tuple[float, list[str]]:
    score = 100.0
    issues = []

    if not description or len(description) < 20:
        score -= 10
        issues.append("Missing or very short business description")
    if not faqs:
        score -= 8
        issues.append("No FAQs provided")
    elif len(faqs) < 2:
        score -= 4
        issues.append("Only 1 FAQ — add more to help customers")
    if not policies.get("return_policy"):
        score -= 6
        issues.append("No return policy specified")
    if not policies.get("shipping_policy"):
        score -= 4
        issues.append("No shipping policy specified")
    if not founded_year:
        score -= 3
        issues.append("Missing founding year")
    if not employee_count:
        score -= 2
        issues.append("Missing employee count")
    if not headquarters:
        score -= 2
        issues.append("Missing headquarters / location")

    for sku, product in catalog.items():
        price = product.get("price", 0)
        name = product.get("name", "")
        desc = product.get("description", "")
        if not price or price <= 0:
            score -= 8
            issues.append(f"Product '{name or sku}' has no price set")
        if not desc or len(desc) < 10:
            score -= 4
            issues.append(f"Product '{name or sku}' has no description")
        if not name:
            score -= 5
            issues.append(f"Product with SKU {sku} has no name")

    return round(max(0.0, min(100.0, score)), 1), issues


class BusinessAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        vertical: str,
        business_type: str,  # "B2C" or "B2B"
        products: list,
        faqs: list,
        policies: dict,
        # company details
        founded_year: Optional[int] = None,
        employee_count: Optional[int] = None,
        annual_revenue: Optional[float] = None,
        headquarters: Optional[str] = None,
        tagline: str = "",
        # B2C: which B2B suppliers to use
        supplier_ids: Optional[list] = None,
        # B2B: wholesale config
        minimum_order_qty: int = 1,
        wholesale_discount: float = 0.0,
        client_b2c_ids: Optional[list] = None,
        event_bus=None,
        message_bus: dict = None,
    ):
        super().__init__(agent_id, name, "business", event_bus, message_bus)
        self.description = description
        self.vertical = vertical
        self.business_type = business_type
        self.catalog = {p["sku"]: dict(p) for p in products}
        self.inventory = {p["sku"]: p.get("stock", 20) for p in products}
        self.faqs = faqs
        self.policies = policies
        self.founded_year = founded_year
        self.employee_count = employee_count
        self.annual_revenue = annual_revenue
        self.headquarters = headquarters
        self.tagline = tagline
        self.supplier_ids = supplier_ids or []
        self.minimum_order_qty = minimum_order_qty
        self.wholesale_discount = wholesale_discount
        self.client_b2c_ids = client_b2c_ids or []
        self.total_revenue = 0.0
        self.orders: list[dict] = []
        self.ratings: dict[str, list[float]] = {}
        self.quality_score, self.quality_issues = compute_quality_score(
            self.catalog, description, faqs, policies, founded_year, employee_count, headquarters
        )

    # ── Serialisation ───────────────────────────────────────────
    def get_state_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "vertical": self.vertical,
            "business_type": self.business_type,
            "founded_year": self.founded_year,
            "employee_count": self.employee_count,
            "annual_revenue": self.annual_revenue,
            "headquarters": self.headquarters,
            "tagline": self.tagline,
            "total_revenue": round(self.total_revenue, 2),
            "order_count": len(self.orders),
            "inventory": dict(self.inventory),
            "catalog": {
                sku: {
                    "name": p.get("name", ""),
                    "price": p.get("price", 0),
                    "rating": p.get("rating", 4.0),
                    "review_count": p.get("review_count", 0),
                    "description": p.get("description", ""),
                }
                for sku, p in self.catalog.items()
            },
            "faqs": self.faqs,
            "policies": self.policies,
            "quality_score": self.quality_score,
            "quality_issues": self.quality_issues,
            "supplier_ids": self.supplier_ids,
            "client_b2c_ids": self.client_b2c_ids,
            "minimum_order_qty": self.minimum_order_qty,
            "wholesale_discount": self.wholesale_discount,
        }

    def restore_from_state(self, state: dict):
        self.total_revenue = state.get("total_revenue", 0.0)
        self.inventory = state.get("inventory", self.inventory)

    # ── Catalog search ──────────────────────────────────────────
    def search_catalog(self, query: str, category: str, max_price: float) -> list:
        results = []
        q_words = query.lower().split()
        for sku, product in self.catalog.items():
            if self.inventory.get(sku, 0) <= 0:
                continue
            price = product.get("price", 0)
            if price <= 0 or price > max_price:
                continue
            name_l = product.get("name", "").lower()
            desc_l = product.get("description", "").lower()
            cat_l = product.get("category", "").lower()
            match = (
                category.lower() in cat_l
                or self.vertical.lower() == category.lower()
                or any(w in name_l or w in desc_l or w in cat_l for w in q_words)
            )
            if match:
                results.append({
                    "sku": sku,
                    "name": product.get("name", ""),
                    "description": product.get("description", ""),
                    "price": price,
                    "category": product.get("category", ""),
                    "merchant_id": self.agent_id,
                    "merchant_name": self.name,
                    "stock": self.inventory.get(sku, 0),
                    "rating": product.get("rating", 4.0),
                    "quality_score": self.quality_score,
                    "has_quality_issues": len(self.quality_issues) > 0,
                })
        return results[:3]

    # ── Run loop ────────────────────────────────────────────────
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
        mtype = msg.message_type
        if mtype == "product_query":
            await self._handle_product_query(msg)
        elif mtype == "question":
            await self._handle_question(msg)
        elif mtype == "place_order":
            await self._handle_order(msg)
        elif mtype == "review":
            await self._handle_review(msg)
        elif mtype == "supply_order":
            asyncio.create_task(self._handle_supply_order(msg))
        elif mtype == "supply_confirmation":
            await self._handle_supply_confirmation(msg)

    # ── B2C: product query ──────────────────────────────────────
    async def _handle_product_query(self, msg):
        query = msg.content.get("query", "")
        category = msg.content.get("category", "")
        max_price = msg.content.get("max_price", 9999)
        txn_id = msg.content.get("transaction_id")
        products = self.search_catalog(query, category, max_price)
        await self.send_message(msg.from_agent_id, "product_response",
            {"products": products, "merchant_name": self.name},
            transaction_id=txn_id,
        )
        if products:
            await self.emit_event(
                "product_query_received",
                {"query": query, "results": len(products), "quality_score": self.quality_score},
                f"{self.name} returned {len(products)} result(s) for \"{query}\"",
                transaction_id=txn_id,
                to_agent_id=msg.from_agent_id,
            )

    # ── B2C: customer question ──────────────────────────────────
    async def _handle_question(self, msg):
        question = msg.content.get("question", "")
        sku = msg.content.get("sku", "")
        txn_id = msg.content.get("transaction_id")
        product = self.catalog.get(sku, {})
        faq_text = " | ".join(f"Q:{f['question']} A:{f['answer']}" for f in self.faqs[:3])
        result = await self.call_llm(
            system=f"You are {self.name}, a {self.vertical} business. Be helpful and concise. Return ONLY valid JSON.",
            user=f"Customer asks about {product.get('name', sku)}: \"{question}\"\nFAQs: {faq_text}\nReturn: {{\"answer\": \"concise answer\"}}",
        )
        answer = result.get("answer", "Please contact our support team for more details.")
        await self.send_message(msg.from_agent_id, "question_answer",
            {"answer": answer, "merchant_name": self.name},
            transaction_id=txn_id,
        )

    # ── B2C: order fulfillment ──────────────────────────────────
    async def _handle_order(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 1)
        price = msg.content.get("price", 0)
        consumer_name = msg.content.get("consumer_name", "Customer")
        txn_id = msg.content.get("transaction_id")

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
            await self.send_message(msg.from_agent_id, "order_confirmation", order,
                transaction_id=txn_id)
            await self.emit_event(
                "order_fulfilled",
                {"order": order, "inventory_left": self.inventory[sku]},
                f"📦 {self.name} fulfilled order for {consumer_name}: "
                f"{self.catalog.get(sku,{}).get('name',sku)} (${price:.2f})",
                transaction_id=txn_id,
                to_agent_id=msg.from_agent_id,
            )
            if self.inventory[sku] <= LOW_INVENTORY_THRESHOLD and self.supplier_ids:
                await self._reorder_from_supplier(sku)
        else:
            await self.send_message(msg.from_agent_id, "order_rejected",
                {"reason": "out of stock", "sku": sku},
                transaction_id=txn_id,
            )
            await self.emit_event(
                "out_of_stock",
                {"sku": sku, "product": self.catalog.get(sku, {}).get("name", sku)},
                f"⚠️ {self.name} is out of stock: {self.catalog.get(sku,{}).get('name',sku)}",
            )

    async def _reorder_from_supplier(self, sku: str):
        supplier_id = random.choice(self.supplier_ids)
        restock_qty = 25
        await self.send_message(supplier_id, "supply_order", {
            "sku": sku,
            "product_name": self.catalog.get(sku, {}).get("name", sku),
            "quantity": restock_qty,
            "merchant_name": self.name,
        })
        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": restock_qty, "supplier": supplier_id},
            f"🔄 {self.name} reordered {restock_qty}x "
            f"{self.catalog.get(sku,{}).get('name',sku)} from supplier",
            to_agent_id=supplier_id,
        )

    # ── B2B: supply order (from another business) ───────────────
    async def _handle_supply_order(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 0)
        product_name = msg.content.get("product_name", sku)
        merchant_name = msg.content.get("merchant_name", "Merchant")

        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": quantity, "from": merchant_name},
            f"🏭 {self.name} received B2B order from {merchant_name}: {quantity}x {product_name}",
            to_agent_id=msg.from_agent_id,
        )
        await asyncio.sleep(random.uniform(2, 5))

        if merchant_name not in self.client_b2c_ids:
            self.client_b2c_ids.append(merchant_name)
        self.total_revenue += quantity * 10  # wholesale revenue estimate

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
            to_agent_id=msg.from_agent_id,
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

    # ── Review ──────────────────────────────────────────────────
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
