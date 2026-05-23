import asyncio
import random
from enum import Enum
from agents.base import BaseAgent
from config import CONSUMER_TICK_SECONDS


class ConsumerState(Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    CONSIDERING = "considering"
    CONVERTING = "converting"
    POST_PURCHASE = "post_purchase"


class ConsumerAgent(BaseAgent):
    def __init__(self, agent_id, name, persona, preferences, budget, event_bus, message_bus, merchant_registry):
        super().__init__(agent_id, name, "consumer", event_bus, message_bus)
        self.persona = persona
        self.preferences = preferences
        self.budget = budget
        self.merchant_registry = merchant_registry
        self.state = ConsumerState.IDLE
        self.purchase_history = []
        self.current_search = {}
        self.candidate_products = []
        self.shortlisted = []
        self.total_spent = 0.0

    def get_state_dict(self):
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "persona": self.persona,
            "preferences": self.preferences,
            "budget": self.budget,
            "state": self.state.value,
            "total_spent": round(self.total_spent, 2),
            "purchase_count": len(self.purchase_history),
        }

    async def run(self):
        await asyncio.sleep(random.uniform(2, 10))
        while self.active:
            try:
                await self.tick()
            except Exception as e:
                print(f"[{self.name}] tick error: {e}")
            await asyncio.sleep(CONSUMER_TICK_SECONDS + random.uniform(-3, 3))

    async def tick(self):
        if self.state == ConsumerState.IDLE:
            if random.random() < 0.65:
                await self._start_discovery()
        elif self.state == ConsumerState.DISCOVERING:
            await self._do_discovery()
        elif self.state == ConsumerState.CONSIDERING:
            await self._do_consideration()
        elif self.state == ConsumerState.CONVERTING:
            await self._do_conversion()
        elif self.state == ConsumerState.POST_PURCHASE:
            await self._do_post_purchase()

    async def _start_discovery(self):
        self.state = ConsumerState.DISCOVERING
        await self.emit_event(
            "state_change",
            {"state": "discovering", "preferences": self.preferences},
            f"{self.name} started browsing — looking for something to buy",
        )

    async def _do_discovery(self):
        result = await self.call_llm(
            system=f"You are {self.name}, a shopper. Preferences: {', '.join(self.preferences)}. Budget: ${self.budget - self.total_spent:.0f} remaining. Return ONLY valid JSON, no explanation.",
            user=f'Decide what to search for. Return: {{"category": "one of {self.preferences}", "query": "2-4 word product search", "max_price": number}}',
        )
        if "error" in result or "category" not in result:
            cat = random.choice(self.preferences)
            result = {"category": cat, "query": f"best {cat} product", "max_price": min(200, self.budget - self.total_spent)}
        self.current_search = result

        relevant = [
            m for m in self.merchant_registry.values()
            if m.vertical in self.preferences or result.get("category", "") == m.vertical
        ]
        if not relevant:
            relevant = list(self.merchant_registry.values())
        selected = random.sample(relevant, min(2, len(relevant)))

        self.candidate_products = []
        for merchant in selected:
            await self.send_message(merchant.agent_id, "product_query", {
                "query": result.get("query", ""),
                "category": result.get("category", ""),
                "max_price": result.get("max_price", self.budget),
            })
            await self.emit_event(
                "product_query",
                {"merchant": merchant.name, "query": result.get("query", "")},
                f"{self.name} asked {merchant.name}: \"{result.get('query', '')}\"",
            )

        await asyncio.sleep(3)

        for _ in range(len(selected)):
            msg = await self.receive_message(timeout=4.0)
            if msg and msg.message_type == "product_response":
                self.candidate_products.extend(msg.content.get("products", []))

        if self.candidate_products:
            self.state = ConsumerState.CONSIDERING
            await self.emit_event(
                "state_change",
                {"state": "considering", "product_count": len(self.candidate_products)},
                f"{self.name} found {len(self.candidate_products)} product(s) to consider",
            )
        else:
            self.state = ConsumerState.IDLE

    async def _do_consideration(self):
        if not self.candidate_products:
            self.state = ConsumerState.IDLE
            return

        affordable = [p for p in self.candidate_products if p.get("price", 9999) <= (self.budget - self.total_spent)]
        if not affordable:
            self.state = ConsumerState.IDLE
            self.candidate_products = []
            return

        product_list = "\n".join(
            f"- {p['name']} ${p['price']} from {p['merchant_name']} SKU:{p['sku']}"
            for p in affordable[:4]
        )
        result = await self.call_llm(
            system=f"You are {self.name}. {self.persona} Budget left: ${self.budget - self.total_spent:.0f}. Return ONLY valid JSON.",
            user=f"Evaluate:\n{product_list}\nReturn: {{\"shortlisted_skus\": [\"sku\"], \"has_question\": true/false, \"question\": \"optional question\"}}",
        )
        if "error" in result or "shortlisted_skus" not in result:
            result = {"shortlisted_skus": [affordable[0]["sku"]], "has_question": False}

        self.shortlisted = [p for p in affordable if p.get("sku") in result.get("shortlisted_skus", [])]
        if not self.shortlisted:
            self.shortlisted = affordable[:1]

        if result.get("has_question") and result.get("question") and self.shortlisted:
            product = self.shortlisted[0]
            merchant_id = product.get("merchant_id")
            if merchant_id:
                await self.send_message(merchant_id, "question", {
                    "sku": product["sku"],
                    "question": result["question"],
                })
                await self.emit_event(
                    "agent_question",
                    {"merchant": product.get("merchant_name"), "question": result["question"]},
                    f"{self.name} asked {product.get('merchant_name', 'merchant')}: \"{result['question']}\"",
                )
                msg = await self.receive_message(timeout=6.0)
                if msg and msg.message_type == "question_answer":
                    await self.emit_event(
                        "agent_answer",
                        {"answer": msg.content.get("answer", "")},
                        f"{product.get('merchant_name', 'Merchant')} replied: \"{msg.content.get('answer', '')}\"",
                    )

        self.state = ConsumerState.CONVERTING
        await self.emit_event(
            "state_change",
            {"state": "converting", "shortlist": len(self.shortlisted)},
            f"{self.name} narrowed down to {len(self.shortlisted)} option(s) — deciding now",
        )

    async def _do_conversion(self):
        if not self.shortlisted:
            self.state = ConsumerState.IDLE
            return

        product_list = "\n".join(
            f"- {p['name']} ${p['price']} from {p['merchant_name']}"
            for p in self.shortlisted
        )
        result = await self.call_llm(
            system=f"You are {self.name}. {self.persona} Remaining budget: ${self.budget - self.total_spent:.0f}. Return ONLY valid JSON.",
            user=f"Final decision:\n{product_list}\nReturn: {{\"decision\": \"buy\" or \"pass\", \"chosen_sku\": \"sku if buying\", \"reasoning\": \"one sentence\"}}",
        )
        if "error" in result:
            result = {"decision": "buy", "chosen_sku": self.shortlisted[0]["sku"], "reasoning": "looks good"}

        if result.get("decision") == "buy":
            chosen = next(
                (p for p in self.shortlisted if p.get("sku") == result.get("chosen_sku")),
                self.shortlisted[0],
            )
            if chosen["price"] <= (self.budget - self.total_spent):
                merchant_id = chosen.get("merchant_id")
                if merchant_id:
                    await self.send_message(merchant_id, "place_order", {
                        "sku": chosen["sku"],
                        "quantity": 1,
                        "price": chosen["price"],
                        "consumer_name": self.name,
                    })
                    msg = await self.receive_message(timeout=6.0)
                    if msg and msg.message_type == "order_confirmation":
                        self.total_spent += chosen["price"]
                        self.purchase_history.append({
                            "sku": chosen["sku"],
                            "name": chosen["name"],
                            "merchant": chosen.get("merchant_name"),
                            "merchant_id": merchant_id,
                            "price": chosen["price"],
                            "order_id": msg.content.get("order_id"),
                        })
                        await self.emit_event(
                            "purchase_completed",
                            {
                                "product": chosen["name"],
                                "merchant": chosen.get("merchant_name"),
                                "price": chosen["price"],
                                "order_id": msg.content.get("order_id"),
                                "reasoning": result.get("reasoning", ""),
                            },
                            f"💰 {self.name} bought {chosen['name']} from {chosen.get('merchant_name')} for ${chosen['price']:.2f}",
                        )
                        self.state = ConsumerState.POST_PURCHASE
                        self.shortlisted = []
                        self.candidate_products = []
                        return
                    elif msg and msg.message_type == "order_rejected":
                        await self.emit_event(
                            "purchase_passed",
                            {"reason": "out of stock"},
                            f"{self.name} couldn't complete purchase — item out of stock",
                        )
            else:
                await self.emit_event(
                    "budget_exceeded",
                    {"product": chosen["name"], "price": chosen["price"]},
                    f"{self.name} passed on {chosen['name']} — over remaining budget",
                )
        else:
            await self.emit_event(
                "purchase_passed",
                {"reasoning": result.get("reasoning", "")},
                f"{self.name} decided not to buy — {result.get('reasoning', 'passed')}",
            )

        self.state = ConsumerState.IDLE
        self.shortlisted = []
        self.candidate_products = []

    async def _do_post_purchase(self):
        if not self.purchase_history:
            self.state = ConsumerState.IDLE
            return

        last = self.purchase_history[-1]
        result = await self.call_llm(
            system=f"You are {self.name}. {self.persona} Return ONLY valid JSON.",
            user=f"You just bought {last['name']} from {last['merchant']} for ${last['price']}. Write a short review. Return: {{\"rating\": 1-5, \"review\": \"1-2 sentence review\"}}",
        )
        if "error" in result:
            result = {"rating": 4, "review": "Good product, happy with my purchase!"}

        merchant_id = last.get("merchant_id")
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
            f"⭐ {self.name} left {result.get('rating', 4)}/5 for {last['name']}: \"{result.get('review', '')}\"",
        )

        self.state = ConsumerState.IDLE
        self.shortlisted = []
        self.candidate_products = []
