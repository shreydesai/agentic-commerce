from typing import Optional
import asyncio
import random
import uuid
from datetime import datetime
from agents.base import BaseAgent
import config
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
        # Store base_price alongside current price so dynamic pricing has an anchor
        self.catalog = {p["sku"]: {**dict(p), "base_price": p.get("price", 0)} for p in products}
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
        self.queries_received: int = 0
        self.queries_converted: int = 0
        self.strategy_notes: list[str] = []     # last 5 LLM strategy insights
        self.last_strategic_review_tick: int = 0

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
            "queries_received": self.queries_received,
            "queries_converted": self.queries_converted,
            "conversion_rate": round(self.queries_converted / max(self.queries_received, 1), 2),
            "strategy_notes": self.strategy_notes[-3:],
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
        await asyncio.sleep(random.uniform(0, 2) / max(config.SIMULATION_SPEED_FACTOR, 0.25))
        tick = 0
        while self.active:
            await self._process_messages()
            tick += 1
            # Proactive inventory check every ~20 s — triggers B2B reorders
            if tick % 20 == 0 and self.business_type == "B2C" and self.supplier_ids:
                await self._proactive_restock()
            # Dynamic pricing every ~30 s — adjust based on inventory levels
            if tick % 30 == 0:
                await self._dynamic_pricing()
            if tick % 50 == 0 and tick > 0:
                await self._strategic_review()
            await asyncio.sleep(1.0 / max(config.SIMULATION_SPEED_FACTOR, 0.25))

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
        elif mtype == "negotiation_request":
            asyncio.create_task(self._handle_negotiation_request(msg))
        elif mtype == "negotiation_accept":
            pass  # Consumer will send a place_order at the agreed price; nothing to do here

    # ── B2C: product query ──────────────────────────────────────
    async def _handle_product_query(self, msg):
        self.queries_received += 1
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
            self.queries_converted += 1
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

    async def _proactive_restock(self):
        """Scan inventory and reorder any SKU at or below threshold."""
        for sku, qty in list(self.inventory.items()):
            if qty <= LOW_INVENTORY_THRESHOLD:
                await self._reorder_from_supplier(sku)

    async def _dynamic_pricing(self):
        """LLM-driven pricing — rules-based fallback if LLM fails/unavailable."""
        conversion_rate = self.queries_converted / max(self.queries_received, 1)

        # Build product summary for LLM
        product_summaries = []
        for sku, product in self.catalog.items():
            base = product.get("base_price", 0)
            if not base or base <= 0:
                continue
            inv = self.inventory.get(sku, 0)
            current_price = product.get("price", base)
            sku_ratings = self.ratings.get(sku, [])
            avg_rating = round(sum(sku_ratings) / len(sku_ratings), 1) if sku_ratings else None
            product_summaries.append({
                "sku": sku,
                "name": product.get("name"),
                "current_price": current_price,
                "base_price": base,
                "inventory": inv,
                "avg_rating": avg_rating,
            })

        if not product_summaries:
            return

        try:
            result = await self.call_llm(
                system=(
                    f"You are the pricing strategist for {self.name}, a {self.vertical} business. "
                    f"Conversion rate: {conversion_rate:.0%} ({self.queries_converted}/{max(self.queries_received,1)} queries). "
                    f"Quality score: {self.quality_score}/100. "
                    f"Constraints: prices must stay within 75%–130% of base_price. "
                    f"Return ONLY valid JSON."
                ),
                user=(
                    f"Products: {product_summaries}\n"
                    f"Suggest price adjustments considering inventory levels, ratings, and conversion rate. "
                    f"Return: {{\"adjustments\": [{{\"sku\": \"X\", \"new_price\": 0.0, \"reason\": \"brief\"}}], "
                    f"\"strategy\": \"one sentence on overall approach\"}}"
                ),
                max_tokens=400,
            )
            if "error" in result:
                raise ValueError(result["error"])
            adjustments = result.get("adjustments", [])
            strategy = result.get("strategy", "")
            if strategy:
                self.strategy_notes.append(strategy)
                if len(self.strategy_notes) > 5:
                    self.strategy_notes = self.strategy_notes[-5:]

            for adj in adjustments:
                sku = adj.get("sku")
                new_price = adj.get("new_price")
                reason = adj.get("reason", "")
                if not sku or not new_price or sku not in self.catalog:
                    continue
                product = self.catalog[sku]
                base = product.get("base_price", 0)
                if not base:
                    continue
                # Clamp to safety range
                new_price = round(max(base * 0.75, min(base * 1.30, new_price)), 2)
                old_price = product.get("price", base)
                if abs(new_price - old_price) > 0.01:
                    product["price"] = new_price
                    direction = "📈" if new_price > old_price else "📉"
                    await self.emit_event(
                        "price_change",
                        {"sku": sku, "product": product.get("name"), "old_price": old_price,
                         "new_price": new_price, "inventory": self.inventory.get(sku, 0),
                         "reason": reason},
                        f"{direction} {self.name} {product.get('name','?')}: "
                        f"${old_price:.2f} → ${new_price:.2f} ({reason})",
                    )
        except Exception:
            # Fallback to rule-based pricing
            for sku, product in self.catalog.items():
                base = product.get("base_price", 0)
                if not base or base <= 0:
                    continue
                inv = self.inventory.get(sku, 0)
                old_price = product.get("price", base)
                if inv <= 5:
                    new_price = round(base * 1.15, 2)
                elif inv >= 60:
                    new_price = round(base * 0.90, 2)
                else:
                    new_price = base
                if abs(new_price - old_price) > 0.01:
                    product["price"] = new_price
                    direction = "📈" if new_price > old_price else "📉"
                    await self.emit_event(
                        "price_change",
                        {"sku": sku, "product": product.get("name"), "old_price": old_price,
                         "new_price": new_price, "inventory": inv},
                        f"{direction} {self.name} {product.get('name','?')}: "
                        f"${old_price:.2f} → ${new_price:.2f} (stock: {inv})",
                    )

    async def _strategic_review(self):
        """LLM assesses market position and suggests improvements."""
        if self.business_type == "B2B":
            return  # B2B strategy review less relevant for now
        conversion_rate = self.queries_converted / max(self.queries_received, 1)

        # Compute overall average rating
        all_ratings = [r for ratings in self.ratings.values() for r in ratings]
        avg_rating = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else None

        try:
            result = await self.call_llm(
                system=(
                    f"You are the strategic advisor for {self.name}. "
                    f"Give a concise, actionable assessment. Return ONLY valid JSON."
                ),
                user=(
                    f"Business metrics:\n"
                    f"- Quality score: {self.quality_score}/100\n"
                    f"- Quality issues: {self.quality_issues}\n"
                    f"- Conversion rate: {conversion_rate:.0%} ({self.queries_converted} orders from {self.queries_received} queries)\n"
                    f"- Average customer rating: {avg_rating or 'no reviews yet'}\n"
                    f"- Total revenue: ${self.total_revenue:.2f}\n"
                    f"- Inventory levels: {dict(list(self.inventory.items())[:4])}\n\n"
                    f"Return: {{\"insight\": \"1-2 sentence assessment\", "
                    f"\"priority_action\": \"one of: improve_descriptions|add_faqs|adjust_pricing|increase_inventory|maintain_course\", "
                    f"\"urgency\": \"high|medium|low\"}}"
                ),
            )
            insight = result.get("insight", "")
            if insight:
                self.strategy_notes.append(f"[Strategy] {insight}")
                if len(self.strategy_notes) > 5:
                    self.strategy_notes = self.strategy_notes[-5:]
                await self.emit_event(
                    "strategy_update",
                    {"insight": insight, "priority_action": result.get("priority_action"),
                     "urgency": result.get("urgency"), "conversion_rate": conversion_rate,
                     "avg_rating": avg_rating},
                    f"🧠 {self.name} strategy review: {insight}",
                )
        except Exception:
            pass

    async def _handle_poor_reviews(self, sku: str, avg_rating: float):
        """When a product has consistently poor reviews, LLM suggests and applies improvements."""
        product = self.catalog.get(sku, {})
        if not product:
            return
        try:
            result = await self.call_llm(
                system=(
                    f"You are the catalog manager for {self.name}. "
                    f"A product has poor reviews. Suggest a concrete improvement. Return ONLY valid JSON."
                ),
                user=(
                    f"Product '{product.get('name', sku)}' has avg rating {avg_rating:.1f}/5. "
                    f"Current description: '{product.get('description', 'none')}'. "
                    f"Return: {{\"improved_description\": \"better product description (1-2 sentences)\", "
                    f"\"insight\": \"why the rating may be low\"}}"
                ),
            )
            new_desc = result.get("improved_description", "")
            insight = result.get("insight", "")
            if new_desc and len(new_desc) > 10:
                old_desc = product.get("description", "")
                product["description"] = new_desc
                await self.emit_event(
                    "catalog_update",
                    {"sku": sku, "product": product.get("name"), "avg_rating": avg_rating,
                     "insight": insight, "old_description": old_desc, "new_description": new_desc},
                    f"📝 {self.name} updated '{product.get('name','?')}' description after {avg_rating:.1f}/5 avg rating",
                )
        except Exception:
            pass

    async def _handle_negotiation_request(self, msg):
        """LLM decides whether to accept, counter, or decline a price negotiation."""
        sku = msg.content.get("sku")
        preferred_price = msg.content.get("preferred_price", 0)
        max_price = msg.content.get("max_price", 0)
        txn_id = msg.content.get("transaction_id")

        product = self.catalog.get(sku, {})
        if not product:
            await self.send_message(msg.from_agent_id, "negotiation_decline",
                {"sku": sku, "transaction_id": txn_id, "reason": "product not found"},
                transaction_id=txn_id)
            return

        current_price = product.get("price", max_price)
        base_price = product.get("base_price", current_price)
        inv = self.inventory.get(sku, 0)
        floor_price = round(base_price * 0.82, 2)  # min 82% of base — won't go below this
        conversion_rate = self.queries_converted / max(self.queries_received, 1)

        try:
            result = await self.call_llm(
                system=(
                    f"You are the sales agent for {self.name}. Make a negotiation decision. Return ONLY valid JSON."
                ),
                user=(
                    f"Customer wants to buy '{product.get('name', sku)}' (listed at ${current_price:.2f}). "
                    f"They prefer ${preferred_price:.2f}, max ${max_price:.2f}. "
                    f"Inventory: {inv} units. Conversion rate: {conversion_rate:.0%}. "
                    f"Floor price (don't go below): ${floor_price:.2f}. "
                    f"Return: {{\"action\": \"accept\" or \"counter\" or \"decline\", "
                    f"\"offered_price\": <price if accept/counter>, "
                    f"\"reason\": \"brief\"}}"
                ),
            )
            action = result.get("action", "decline")
            offered_price = result.get("offered_price", current_price)
            # Safety: clamp to floor
            offered_price = max(floor_price, min(current_price, round(float(offered_price), 2)))

            if action in ("accept", "counter"):
                await self.send_message(msg.from_agent_id, "counter_offer", {
                    "sku": sku,
                    "transaction_id": txn_id,
                    "offered_price": offered_price,
                    "original_price": current_price,
                    "offer_type": action,
                    "reason": result.get("reason", ""),
                }, transaction_id=txn_id)
            else:
                await self.send_message(msg.from_agent_id, "negotiation_decline", {
                    "sku": sku,
                    "transaction_id": txn_id,
                    "reason": result.get("reason", "Price is firm"),
                }, transaction_id=txn_id)
        except Exception:
            # Fallback: make a simple rule-based decision
            if inv > 15 and preferred_price >= floor_price:
                # Plenty of stock, accept a reasonable offer
                offered_price = max(floor_price, min(current_price, preferred_price))
                await self.send_message(msg.from_agent_id, "counter_offer", {
                    "sku": sku, "transaction_id": txn_id,
                    "offered_price": offered_price, "original_price": current_price,
                    "offer_type": "counter", "reason": "Happy to help",
                }, transaction_id=txn_id)
            else:
                await self.send_message(msg.from_agent_id, "negotiation_decline", {
                    "sku": sku, "transaction_id": txn_id, "reason": "Price is firm at this stock level",
                }, transaction_id=txn_id)

    async def _reorder_from_supplier(self, sku: str):
        supplier_id = random.choice(self.supplier_ids)
        restock_qty = 25
        supply_txn_id = f"SUP-{str(uuid.uuid4())[:6].upper()}"
        product_name = self.catalog.get(sku, {}).get("name", sku)

        # Record the supply transaction so it appears in the Transactions panel
        await self.emit_event(
            "transaction_update",
            {"transaction": {
                "transaction_id": supply_txn_id,
                "type": "supply",
                "consumer_id": self.agent_id,
                "consumer_name": self.name,
                "supplier_id": supplier_id,
                "supplier_name": supplier_id.replace("biz_", "").replace("_", " ").title(),
                "sku": sku,
                "product_name": product_name,
                "quantity": restock_qty,
                "status": "supply_ordered",
                "funnel_steps": [{"stage": "ordered",
                    "details": f"Reordering {restock_qty}x {product_name}",
                    "timestamp": datetime.utcnow().isoformat()}],
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
            }, "status": "supply_ordered"},
            transaction_id=supply_txn_id,
        )
        # Include supply_txn_id in the message content so the supplier can thread it back
        await self.send_message(supplier_id, "supply_order", {
            "sku": sku,
            "product_name": product_name,
            "quantity": restock_qty,
            "merchant_name": self.name,
            "supply_txn_id": supply_txn_id,
        }, transaction_id=supply_txn_id)
        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": restock_qty, "supplier": supplier_id},
            f"🔄 {self.name} reordered {restock_qty}x {product_name} from supplier",
            to_agent_id=supplier_id,
            transaction_id=supply_txn_id,
        )

    # ── B2B: supply order (from another business) ───────────────
    async def _handle_supply_order(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 0)
        product_name = msg.content.get("product_name", sku)
        merchant_name = msg.content.get("merchant_name", "Merchant")
        supply_txn_id = msg.content.get("supply_txn_id")

        await self.emit_event(
            "supply_order_sent",
            {"sku": sku, "quantity": quantity, "from": merchant_name},
            f"🏭 {self.name} received B2B order from {merchant_name}: {quantity}x {product_name}",
            to_agent_id=msg.from_agent_id,
            transaction_id=supply_txn_id,
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
            "supply_txn_id": supply_txn_id,   # thread the ID back to the orderer
        }, transaction_id=supply_txn_id)
        await self.emit_event(
            "supply_order_fulfilled",
            {"sku": sku, "quantity": quantity, "to": merchant_name},
            f"🚚 {self.name} shipped {quantity}x {product_name} → {merchant_name}",
            to_agent_id=msg.from_agent_id,
            transaction_id=supply_txn_id,
        )

    async def _handle_supply_confirmation(self, msg):
        sku = msg.content.get("sku")
        quantity = msg.content.get("quantity", 0)
        supplier_name = msg.content.get("supplier_name", "Supplier")
        supply_txn_id = msg.content.get("supply_txn_id")
        product_name = self.catalog.get(sku, {}).get("name", sku)
        if sku in self.inventory:
            self.inventory[sku] += quantity
        if supply_txn_id:
            now_iso = datetime.utcnow().isoformat()
            await self.emit_event(
                "transaction_update",
                {"transaction": {
                    "transaction_id": supply_txn_id,
                    "type": "supply",
                    "consumer_id": self.agent_id,
                    "consumer_name": self.name,
                    "supplier_name": supplier_name,
                    "sku": sku,
                    "product_name": product_name,
                    "quantity": quantity,
                    "status": "completed",
                    "completed_at": now_iso,
                    "funnel_steps": [
                        {"stage": "ordered",
                         "details": f"Reordered {quantity}x {product_name}",
                         "timestamp": now_iso},
                        {"stage": "confirmed",
                         "details": f"{supplier_name} confirmed shipment",
                         "timestamp": now_iso},
                        {"stage": "received",
                         "details": f"+{quantity} units added to inventory",
                         "timestamp": now_iso},
                    ],
                }, "status": "completed"},
                f"✅ Supply transaction {supply_txn_id} completed",
                transaction_id=supply_txn_id,
            )
        await self.emit_event(
            "supply_received",
            {"sku": sku, "quantity": quantity, "supplier": supplier_name},
            f"✅ {self.name} received {quantity}x {product_name} from {supplier_name}",
            transaction_id=supply_txn_id,
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
        # If avg rating for this SKU is poor, trigger quality improvement response
        if sku in self.ratings and len(self.ratings[sku]) >= 2:
            avg = sum(self.ratings[sku]) / len(self.ratings[sku])
            if avg < 3.2:
                asyncio.create_task(self._handle_poor_reviews(sku, avg))
