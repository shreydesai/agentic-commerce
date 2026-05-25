from typing import Optional
import asyncio
import random
import uuid
from enum import Enum
from agents.base import BaseAgent
import config
from config import CONSUMER_TICK_SECONDS


class ConsumerState(Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    CONSIDERING = "considering"
    CONVERTING = "converting"
    POST_PURCHASE = "post_purchase"


class ConsumerAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        # demographics
        name: str,
        age: int,
        gender: str,
        occupation: str,
        annual_income: float,
        education: str,
        location: str,
        household_size: int,
        # behavior
        shopping_interests: list[str],
        price_sensitivity: float,   # 0-1
        brand_loyalty: float,        # 0-1
        impulse_tendency: float,     # 0-1
        research_depth: float,       # 0-1
        preferred_channels: list[str],
        # financial
        budget: float,
        credit_score: int,
        # persona summary
        persona: str,
        event_bus=None,
        message_bus: dict = None,
        business_registry: dict = None,
    ):
        super().__init__(agent_id, name, "consumer", event_bus, message_bus)
        self.age = age
        self.gender = gender
        self.occupation = occupation
        self.annual_income = annual_income
        self.education = education
        self.location = location
        self.household_size = household_size
        self.shopping_interests = shopping_interests
        self.price_sensitivity = price_sensitivity
        self.brand_loyalty = brand_loyalty
        self.impulse_tendency = impulse_tendency
        self.research_depth = research_depth
        self.preferred_channels = preferred_channels
        self.budget = budget
        self.credit_score = credit_score
        self.persona = persona
        self.business_registry = business_registry or {}

        self.state = ConsumerState.IDLE
        self.total_spent = 0.0
        self.purchase_history: list[dict] = []
        self.merchant_satisfaction: dict[str, list[float]] = {}
        self.current_transaction: Optional[dict] = None
        self.candidate_products: list[dict] = []
        self.shortlisted: list[dict] = []

    # ── Serialization ───────────────────────────────────────────
    def get_state_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "occupation": self.occupation,
            "annual_income": self.annual_income,
            "education": self.education,
            "location": self.location,
            "household_size": self.household_size,
            "shopping_interests": self.shopping_interests,
            "price_sensitivity": self.price_sensitivity,
            "brand_loyalty": self.brand_loyalty,
            "impulse_tendency": self.impulse_tendency,
            "research_depth": self.research_depth,
            "preferred_channels": self.preferred_channels,
            "budget": self.budget,
            "credit_score": self.credit_score,
            "persona": self.persona,
            "state": self.state.value,
            "total_spent": round(self.total_spent, 2),
            "purchase_count": len(self.purchase_history),
            "current_transaction_id": (self.current_transaction or {}).get("transaction_id"),
            "merchant_satisfaction": {
                k: round(sum(v) / len(v), 1)
                for k, v in self.merchant_satisfaction.items()
                if v
            },
        }

    def restore_from_state(self, state: dict):
        self.total_spent = state.get("total_spent", 0.0)
        self.purchase_history = state.get("purchase_history", [])
        self.merchant_satisfaction = state.get("merchant_satisfaction_raw", {})

    def _new_transaction(self) -> dict:
        return {
            "transaction_id": f"TXN-{str(uuid.uuid4())[:6].upper()}",
            "consumer_id": self.agent_id,
            "consumer_name": self.name,
            "status": "discovering",
            "funnel_steps": [],
            "businesses_contacted": [],
            "products_considered": [],
            "shortlisted": [],
            "final_product": None,
            "final_merchant": None,
            "total": None,
            "started_at": None,
            "completed_at": None,
        }

    def _txn_step(self, stage: str, details: str):
        from datetime import datetime
        if self.current_transaction:
            self.current_transaction["funnel_steps"].append({
                "stage": stage, "details": details,
                "timestamp": datetime.utcnow().isoformat(),
            })

    def _txn_id(self) -> Optional[str]:
        return (self.current_transaction or {}).get("transaction_id")

    # ── Run loop ────────────────────────────────────────────────
    async def run(self):
        spf = config.SIMULATION_SPEED_FACTOR
        await asyncio.sleep(random.uniform(2, 10) / max(spf, 0.25))
        while self.active:
            try:
                await self.tick()
            except Exception as e:
                print(f"[{self.name}] tick error: {e}")
            spf = config.SIMULATION_SPEED_FACTOR
            await asyncio.sleep((CONSUMER_TICK_SECONDS + random.uniform(-3, 3)) / max(spf, 0.25))

    async def tick(self):
        if self.state == ConsumerState.IDLE:
            # Higher impulse → more likely to start shopping
            threshold = 0.4 + self.impulse_tendency * 0.3
            if random.random() < threshold:
                await self._start_discovery()
        elif self.state == ConsumerState.DISCOVERING:
            await self._do_discovery()
        elif self.state == ConsumerState.CONSIDERING:
            await self._do_consideration()
        elif self.state == ConsumerState.CONVERTING:
            await self._do_conversion()
        elif self.state == ConsumerState.POST_PURCHASE:
            await self._do_post_purchase()

    # ── Discovery ───────────────────────────────────────────────
    async def _start_discovery(self):
        from datetime import datetime
        self.state = ConsumerState.DISCOVERING
        self.current_transaction = self._new_transaction()
        self.current_transaction["started_at"] = datetime.utcnow().isoformat()
        self._txn_step("discovering", "Started browsing")
        await self.emit_event(
            "state_change",
            {"state": "discovering", "preferences": self.shopping_interests},
            f"{self.name} started browsing — looking for something to buy",
            transaction_id=self._txn_id(),
        )
        await self._emit_transaction_update("discovering")

    async def _do_discovery(self):
        remaining = self.budget - self.total_spent
        result = await self.call_llm(
            system=(
                f"You are {self.name}, {self.age}yo {self.gender} {self.occupation}. "
                f"Income: ${self.annual_income:,.0f}. Location: {self.location}. "
                f"Interests: {', '.join(self.shopping_interests)}. "
                f"Price sensitivity: {self.price_sensitivity:.1f}/1. "
                f"Budget left: ${remaining:.0f}. Return ONLY valid JSON."
            ),
            user=f'What to shop for? Return: {{"category": "one of {self.shopping_interests}", "query": "2-4 word search", "max_price": number}}',
        )
        if "error" in result or "category" not in result:
            cat = random.choice(self.shopping_interests)
            result = {"category": cat, "query": f"best {cat} product", "max_price": min(150, remaining)}

        self._txn_step("discovering", f"Searching for: {result.get('query','')} (category: {result.get('category','')})")

        # Find relevant B2C businesses
        relevant = [
            b for b in self.business_registry.values()
            if b.business_type == "B2C"
            and (b.vertical == result.get("category", "") or b.vertical in self.shopping_interests)
        ]
        if not relevant:
            relevant = [b for b in self.business_registry.values() if b.business_type == "B2C"]
        # Contact more businesses in parallel for a richer product mix
        selected = random.sample(relevant, min(4, len(relevant)))

        self.candidate_products = []
        # Fire all queries first (non-blocking), then collect responses
        for biz in selected:
            if biz.agent_id not in (self.current_transaction or {}).get("businesses_contacted", []):
                (self.current_transaction or {}).setdefault("businesses_contacted", []).append(biz.agent_id)
            await self.send_message(biz.agent_id, "product_query", {
                "query": result.get("query", ""),
                "category": result.get("category", ""),
                "max_price": result.get("max_price", remaining),
                "transaction_id": self._txn_id(),
            }, transaction_id=self._txn_id())
            await self.emit_event(
                "product_query",
                {"merchant": biz.name, "query": result.get("query", ""), "quality_score": biz.quality_score},
                f"{self.name} asked {biz.name}: \"{result.get('query','')}\"",
                transaction_id=self._txn_id(),
                to_agent_id=biz.agent_id,
            )

        # Give businesses time to respond (they process messages on their own loop)
        await asyncio.sleep(2)
        for _ in range(len(selected)):
            msg = await self.receive_message(timeout=3.0)
            if msg and msg.message_type == "product_response":
                self.candidate_products.extend(msg.content.get("products", []))

        if self.candidate_products:
            if self.current_transaction:
                self.current_transaction["products_considered"] = [
                    {"sku": p["sku"], "name": p["name"], "merchant": p["merchant_name"]}
                    for p in self.candidate_products
                ]
            self.state = ConsumerState.CONSIDERING
            self._txn_step("considering", f"Found {len(self.candidate_products)} products")
            await self.emit_event(
                "state_change",
                {"state": "considering", "product_count": len(self.candidate_products)},
                f"{self.name} found {len(self.candidate_products)} product(s) to consider",
                transaction_id=self._txn_id(),
            )
            await self._emit_transaction_update("considering")
        else:
            self._end_transaction("abandoned")
            self.state = ConsumerState.IDLE

    # ── Consideration ───────────────────────────────────────────
    async def _do_consideration(self):
        remaining = self.budget - self.total_spent
        affordable = [p for p in self.candidate_products if p.get("price", 9999) <= remaining]
        if not affordable:
            self._end_transaction("abandoned")
            self.state = ConsumerState.IDLE
            self.candidate_products = []
            return

        # Include quality score in consideration prompt to show impact of imperfect catalogs
        product_list = "\n".join(
            f"- {p['name']} ${p['price']:.2f} from {p['merchant_name']} "
            f"[quality: {p.get('quality_score', 100):.0f}/100"
            + (" ⚠️ incomplete catalog" if p.get("has_quality_issues") else "") + f"] SKU:{p['sku']}"
            for p in affordable[:5]
        )

        # Research depth affects how likely they are to ask questions
        ask_question = self.research_depth > 0.5 and random.random() < self.research_depth

        # Build recent purchase context for the LLM
        history_ctx = ""
        if self.purchase_history:
            recent = self.purchase_history[-5:]
            lines = []
            for p in recent:
                merch_ratings = self.merchant_satisfaction.get(p.get("merchant_id", ""), [])
                avg_rating = round(sum(merch_ratings) / len(merch_ratings), 1) if merch_ratings else "?"
                lines.append(f"  - Bought '{p['name']}' from {p['merchant']} (rated: {avg_rating}/5)")
            history_ctx = f"\nRecent purchase history:\n" + "\n".join(lines)

        result = await self.call_llm(
            system=(
                f"You are {self.name}. {self.persona} "
                f"Budget left: ${remaining:.0f}. "
                f"Price sensitivity: {self.price_sensitivity:.1f}/1 (higher=more price-conscious). "
                f"Prefer reliable sellers with complete product information. Return ONLY valid JSON."
                + history_ctx
            ),
            user=(
                f"Evaluate these products:\n{product_list}\n"
                f"Return: {{\"shortlisted_skus\": [\"sku\"], "
                f"\"has_question\": {'true' if ask_question else 'false'}, "
                f"\"question\": \"optional question for merchant\"}}"
            ),
        )
        if "error" in result or "shortlisted_skus" not in result:
            result = {"shortlisted_skus": [affordable[0]["sku"]], "has_question": False}

        self.shortlisted = [p for p in affordable if p.get("sku") in result.get("shortlisted_skus", [])]
        if not self.shortlisted:
            self.shortlisted = affordable[:1]

        if self.current_transaction:
            self.current_transaction["shortlisted"] = [
                {"sku": p["sku"], "name": p["name"], "merchant": p["merchant_name"]}
                for p in self.shortlisted
            ]
        self._txn_step("considering", f"Shortlisted {len(self.shortlisted)} product(s)")

        if result.get("has_question") and result.get("question") and self.shortlisted:
            product = self.shortlisted[0]
            merchant_id = product.get("merchant_id")
            if merchant_id:
                await self.send_message(merchant_id, "question", {
                    "sku": product["sku"],
                    "question": result["question"],
                    "transaction_id": self._txn_id(),
                }, transaction_id=self._txn_id())
                await self.emit_event(
                    "agent_question",
                    {"merchant": product.get("merchant_name"), "question": result["question"]},
                    f"{self.name} asked {product.get('merchant_name','merchant')}: \"{result['question']}\"",
                    transaction_id=self._txn_id(),
                    to_agent_id=merchant_id,
                )
                msg = await self.receive_message(timeout=6.0)
                if msg and msg.message_type == "question_answer":
                    self._txn_step("considering", f"Q&A: {result['question']} → {msg.content.get('answer','')}")
                    await self.emit_event(
                        "agent_answer",
                        {"answer": msg.content.get("answer", "")},
                        f"{product.get('merchant_name','Merchant')} replied: \"{msg.content.get('answer','')}\"",
                        transaction_id=self._txn_id(),
                    )

        self.state = ConsumerState.CONVERTING
        await self.emit_event(
            "state_change",
            {"state": "converting", "shortlist": len(self.shortlisted)},
            f"{self.name} narrowed to {len(self.shortlisted)} option(s) — deciding now",
            transaction_id=self._txn_id(),
        )
        await self._emit_transaction_update("converting")

    # ── Conversion ──────────────────────────────────────────────
    async def _do_conversion(self):
        if not self.shortlisted:
            self._end_transaction("abandoned")
            await self._emit_transaction_update("abandoned")
            self.state = ConsumerState.IDLE
            return

        remaining = self.budget - self.total_spent
        product_list = "\n".join(
            f"- {p['name']} ${p['price']:.2f} from {p['merchant_name']} "
            f"[quality: {p.get('quality_score',100):.0f}/100]"
            for p in self.shortlisted
        )

        merchant_ctx = ""
        if self.shortlisted and self.merchant_satisfaction:
            parts = []
            for p in self.shortlisted:
                mid = p.get("merchant_id", "")
                ratings = self.merchant_satisfaction.get(mid, [])
                if ratings:
                    avg = round(sum(ratings) / len(ratings), 1)
                    parts.append(f"  - {p['merchant_name']}: your past avg rating = {avg}/5")
            if parts:
                merchant_ctx = "\nYour history with these merchants:\n" + "\n".join(parts)

        result = await self.call_llm(
            system=(
                f"You are {self.name}. {self.persona} "
                f"Budget left: ${remaining:.0f}. "
                f"Impulse tendency: {self.impulse_tendency:.1f}/1. Return ONLY valid JSON."
                + merchant_ctx
            ),
            user=(
                f"Final decision:\n{product_list}\n"
                f"Return: {{\"decision\": \"buy\" or \"pass\", \"chosen_sku\": \"sku if buying\", \"reasoning\": \"one sentence\"}}"
            ),
        )
        if "error" in result:
            result = {"decision": "buy", "chosen_sku": self.shortlisted[0]["sku"], "reasoning": "looks good"}

        if result.get("reasoning"):
            self._txn_step("deciding", f"Reasoning: {result['reasoning']}")

        if result.get("decision") == "buy":
            chosen = next(
                (p for p in self.shortlisted if p.get("sku") == result.get("chosen_sku")),
                self.shortlisted[0],
            )
            if chosen["price"] <= remaining:
                merchant_id = chosen.get("merchant_id")

                # Attempt negotiation if consumer is price-sensitive and price seems high
                # preferred_price is 80% of max_price from discovery (approximated as 90% of listed price)
                preferred_price = round(chosen["price"] * 0.88, 2)
                should_negotiate = (
                    self.price_sensitivity > 0.52
                    and self.research_depth > 0.35
                    and chosen["price"] > preferred_price
                    and merchant_id is not None
                )
                agreed_price = chosen["price"]  # default to full price
                if should_negotiate:
                    await self.send_message(merchant_id, "negotiation_request", {
                        "sku": chosen["sku"],
                        "preferred_price": preferred_price,
                        "max_price": chosen["price"],
                        "transaction_id": self._txn_id(),
                        "reason": f"Budget-conscious — hoping for a small discount",
                    }, transaction_id=self._txn_id())
                    self._txn_step("negotiating", f"Requested discount: ${chosen['price']:.2f} → ${preferred_price:.2f} preferred")
                    neg_msg = await self.receive_message(timeout=5.0)
                    if neg_msg and neg_msg.message_type == "counter_offer":
                        offered = neg_msg.content.get("offered_price", chosen["price"])
                        if offered <= chosen["price"]:  # any reduction is acceptable
                            # Accept the counter-offer
                            await self.send_message(merchant_id, "negotiation_accept", {
                                "sku": chosen["sku"],
                                "transaction_id": self._txn_id(),
                                "agreed_price": offered,
                            }, transaction_id=self._txn_id())
                            agreed_price = offered
                            self._txn_step("negotiating", f"Accepted counter-offer: ${offered:.2f} (saved ${chosen['price']-offered:.2f})")
                        else:
                            self._txn_step("negotiating", "Counter too high, proceeding at full price")
                    elif neg_msg and neg_msg.message_type == "negotiation_decline":
                        self._txn_step("negotiating", "Merchant declined — proceeding at full price")
                    # If timeout or no response, proceed at full price (agreed_price stays as chosen["price"])

                if merchant_id:
                    await self.send_message(merchant_id, "place_order", {
                        "sku": chosen["sku"],
                        "quantity": 1,
                        "price": agreed_price,
                        "consumer_name": self.name,
                        "transaction_id": self._txn_id(),
                    }, transaction_id=self._txn_id())
                    msg = await self.receive_message(timeout=6.0)
                    if msg and msg.message_type == "order_confirmation":
                        self.total_spent += agreed_price
                        purchase = {
                            "sku": chosen["sku"],
                            "name": chosen["name"],
                            "merchant": chosen.get("merchant_name"),
                            "merchant_id": merchant_id,
                            "price": agreed_price,
                            "order_id": msg.content.get("order_id"),
                            "transaction_id": self._txn_id(),
                        }
                        self.purchase_history.append(purchase)
                        self._txn_step("completed", f"Purchased {chosen['name']} for ${agreed_price:.2f}")
                        self._end_transaction(
                            "completed",
                            final_product=chosen["name"],
                            final_merchant=chosen.get("merchant_name"),
                            total=agreed_price,
                        )
                        await self._emit_transaction_update("completed")
                        await self.emit_event(
                            "purchase_completed",
                            {
                                "product": chosen["name"],
                                "merchant": chosen.get("merchant_name"),
                                "price": agreed_price,
                                "order_id": msg.content.get("order_id"),
                                "reasoning": result.get("reasoning", ""),
                            },
                            f"💰 {self.name} bought {chosen['name']} from {chosen.get('merchant_name')} for ${agreed_price:.2f}",
                            transaction_id=self._txn_id(),
                        )
                        self.state = ConsumerState.POST_PURCHASE
                        self.shortlisted = []
                        self.candidate_products = []
                        return
                    elif msg and msg.message_type == "order_rejected":
                        self._txn_step("abandoned", "Item out of stock")
            else:
                self._txn_step("abandoned", f"Over budget: ${chosen['price']:.2f} > ${remaining:.2f}")
                await self.emit_event(
                    "budget_exceeded",
                    {"product": chosen["name"], "price": chosen["price"]},
                    f"{self.name} passed on {chosen['name']} — over remaining budget",
                    transaction_id=self._txn_id(),
                )
        else:
            self._txn_step("abandoned", f"Decided not to buy: {result.get('reasoning','')}")
            await self.emit_event(
                "purchase_passed",
                {"reasoning": result.get("reasoning", "")},
                f"{self.name} decided not to buy — {result.get('reasoning','passed')}",
                transaction_id=self._txn_id(),
            )

        self._end_transaction("abandoned")
        await self._emit_transaction_update("abandoned")
        self.state = ConsumerState.IDLE
        self.shortlisted = []
        self.candidate_products = []

    # ── Post-purchase ───────────────────────────────────────────
    async def _do_post_purchase(self):
        if not self.purchase_history:
            self.state = ConsumerState.IDLE
            return
        last = self.purchase_history[-1]
        result = await self.call_llm(
            system=f"You are {self.name}. {self.persona} Return ONLY valid JSON.",
            user=(
                f"You just bought {last['name']} from {last['merchant']} for ${last['price']}. "
                f"Write a short review. Return: {{\"rating\": 1-5, \"review\": \"1-2 sentence review\"}}"
            ),
        )
        if "error" in result:
            result = {"rating": 4, "review": "Good product, happy with my purchase!"}

        # Update merchant satisfaction history
        rating = result.get("rating", 4)
        merchant_id = last.get("merchant_id")
        if merchant_id:
            if merchant_id not in self.merchant_satisfaction:
                self.merchant_satisfaction[merchant_id] = []
            self.merchant_satisfaction[merchant_id].append(rating)
            # Keep last 10 ratings per merchant
            if len(self.merchant_satisfaction[merchant_id]) > 10:
                self.merchant_satisfaction[merchant_id] = self.merchant_satisfaction[merchant_id][-10:]

        # Evolve traits based on purchase outcome (small nudges, clamped 0–1)
        if rating >= 4:
            # Good experience: slightly more brand-loyal, slightly less price-anxious
            self.brand_loyalty = min(1.0, self.brand_loyalty + 0.02)
            self.price_sensitivity = max(0.0, self.price_sensitivity - 0.01)
        elif rating <= 2:
            # Bad experience: less loyal, more price-cautious, more research next time
            self.brand_loyalty = max(0.0, self.brand_loyalty - 0.03)
            self.price_sensitivity = min(1.0, self.price_sensitivity + 0.02)
            self.research_depth = min(1.0, self.research_depth + 0.02)

        if merchant_id:
            await self.send_message(merchant_id, "review", {
                "sku": last["sku"],
                "rating": result.get("rating", 4),
                "review": result.get("review", ""),
                "consumer_name": self.name,
            })
        await self.emit_event(
            "review_posted",
            {
                "product": last["name"],
                "merchant": last.get("merchant"),
                "rating": result.get("rating", 4),
                "review": result.get("review", ""),
            },
            f"⭐ {self.name} left {result.get('rating',4)}/5 for {last['name']}: \"{result.get('review','')}\"",
            transaction_id=last.get("transaction_id"),
        )
        self.state = ConsumerState.IDLE
        self.shortlisted = []
        self.candidate_products = []

    # ── Helpers ──────────────────────────────────────────────────
    def _end_transaction(self, status: str, final_product=None, final_merchant=None, total=None):
        from datetime import datetime
        if not self.current_transaction:
            return
        self.current_transaction["status"] = status
        self.current_transaction["completed_at"] = datetime.utcnow().isoformat()
        if final_product:
            self.current_transaction["final_product"] = final_product
        if final_merchant:
            self.current_transaction["final_merchant"] = final_merchant
        if total is not None:
            self.current_transaction["total"] = total

    async def _emit_transaction_update(self, status: str):
        if not self.current_transaction:
            return
        await self.emit_event(
            "transaction_update",
            {"transaction": dict(self.current_transaction), "status": status},
            "",
            transaction_id=self._txn_id(),
        )
