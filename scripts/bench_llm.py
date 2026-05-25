#!/usr/bin/env python3
"""
bench_llm.py — LLM concurrency benchmark

Tests throughput, latency, and failure rates at varying concurrency levels
using prompts that faithfully replicate what agents/consumer.py and
agents/business.py actually send. Use results to tune the global semaphore
limit in agents/base.py.

Prompt scenarios (all replicated from production code):
  consumer_discovery    — what to search for today (~290 in / 120 out tokens)
  consumer_consider     — shortlist 5 products   (~380 in / 140 out tokens)
  consumer_convert      — final buy/pass decision (~200 in / 100 out tokens)
  consumer_review       — post-purchase rating    (~240 in /  90 out tokens)
  business_qa           — answer customer question (~150 in /  80 out tokens)
  business_pricing      — dynamic price adjustment (~310 in / 200 out tokens)
  business_strategy     — strategic review         (~240 in / 140 out tokens)
  business_negotiation  — price negotiation        (~190 in /  90 out tokens)
  sim_mix               — weighted mix of all above (matches live sim ratios)

Usage:
  python3 scripts/bench_llm.py                                     # defaults
  python3 scripts/bench_llm.py --scenario sim_mix --concurrency 1 3 5 10 15 20
  python3 scripts/bench_llm.py --scenario consumer_review --requests 30
  python3 scripts/bench_llm.py --scenario business_pricing --max-tokens 256  # repro prod truncation
  python3 scripts/bench_llm.py --list-scenarios
  python3 scripts/bench_llm.py --list-providers

Key flags:
  --max-tokens N    Override per-scenario token budgets with a fixed value.
                    Use 256 to reproduce the production setting in base.py and
                    confirm which call types get truncated.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Simulation prompt library ─────────────────────────────────────────────────
# Each entry mirrors the exact system/user construction in consumer.py /
# business.py. Persona, product names, prices, etc. are representative samples.

class SimPrompts:
    """Returns (system, user, max_tokens) tuples that match live agent calls."""

    # ── Consumer: _do_discovery ───────────────────────────────────
    @staticmethod
    def consumer_discovery() -> tuple[str, str, int]:
        return (
            (
                "You are Alex Chen, 28yo male Software Engineer. "
                "Income: $145,000/year. Location: San Francisco, CA. "
                "Interests: electronics, gaming, home. "
                "Price sensitivity: 0.3/1 (1=very price conscious). "
                "Budget remaining: $820. "
                "Recent purchases: Logitech MX Master 3 Mouse, Sony WH-1000XM5 Headphones. "
                "Return ONLY valid JSON."
            ),
            (
                "You need to shop for something today. Based on your profile and interests, decide what to look for.\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"category\": \"one of ['electronics', 'gaming', 'home']\",\n"
                "  \"query\": \"specific 3-6 word search — be precise, not generic. e.g. 'wireless earbuds for running under $80' not 'best electronics'\",\n"
                "  \"max_price\": <realistic price given budget and income>,\n"
                "  \"shopping_intent\": \"one word: replenishing|upgrading|gifting|treating|exploring\",\n"
                "  \"urgency\": \"high|medium|low\"\n"
                "}"
            ),
            120,
        )

    # ── Consumer: _do_consideration ───────────────────────────────
    @staticmethod
    def consumer_consideration() -> tuple[str, str, int]:
        return (
            (
                "You are Alex Chen. Tech-savvy software engineer who researches thoroughly before buying. "
                "Prefers premium products with good reviews. "
                "Budget left: $820. "
                "Shopping intent today: upgrading. "
                "Price sensitivity: 0.3/1 (higher=more price-conscious). "
                "Do not shortlist products over $902.00 (1.1x remaining budget — too risky). "
                "Prefer reliable sellers with complete product information. Return ONLY valid JSON.\n"
                "Recent purchase history:\n"
                "  - Bought 'Logitech MX Master 3 Mouse' from TechZone Electronics (rated: 5.0/5)\n"
                "  - Bought 'Sony WH-1000XM5 Headphones' from WiredWorld (rated: 4.0/5)"
            ),
            (
                "Evaluate these products:\n"
                "- Samsung 65\" 4K QLED TV $899.99 from TechZone Electronics [quality: 95/100] SKU:TECH-TV-001\n"
                "- LG C3 65\" OLED TV $849.00 from WiredWorld [quality: 92/100] SKU:WIRE-TV-002\n"
                "- Sony X90L 65\" TV $799.00 from TechZone Electronics [quality: 95/100] SKU:TECH-TV-003\n"
                "- Hisense U8K 65\" TV $649.99 from WiredWorld [quality: 92/100] SKU:WIRE-TV-004\n"
                "- TCL 6-Series 65\" TV $499.99 from BargainBin [quality: 41/100 ⚠️ incomplete catalog] SKU:BARG-TV-005\n"
                "Return: {\"shortlisted_skus\": [\"sku\"], "
                "\"has_question\": false, "
                "\"question\": \"optional question for merchant\"}"
            ),
            160,
        )

    # ── Consumer: _do_conversion ──────────────────────────────────
    @staticmethod
    def consumer_convert() -> tuple[str, str, int]:
        return (
            (
                "You are Alex Chen. Tech-savvy software engineer who researches thoroughly before buying. "
                "Budget left: $820. "
                "Impulse tendency: 0.2/1. Return ONLY valid JSON.\n"
                "Your history with these merchants:\n"
                "  - TechZone Electronics: your past avg rating = 5.0/5\n"
                "  - WiredWorld: your past avg rating = 4.0/5"
            ),
            (
                "Final decision:\n"
                "- Samsung 65\" 4K QLED TV $899.99 from TechZone Electronics [quality: 95/100]\n"
                "- LG C3 65\" OLED TV $849.00 from WiredWorld [quality: 92/100]\n"
                "Return: {\"decision\": \"buy\" or \"pass\", \"chosen_sku\": \"sku if buying\", \"reasoning\": \"one sentence\"}"
            ),
            120,
        )

    # ── Consumer: _do_post_purchase ───────────────────────────────
    @staticmethod
    def consumer_review() -> tuple[str, str, int]:
        persona = "Tech-savvy software engineer who researches thoroughly before buying. Prefers premium products with good reviews."
        return (
            f"You are Alex Chen. {persona} Return ONLY valid JSON.",
            (
                "You just received Samsung 65\" 4K QLED TV from TechZone Electronics — you paid $849.99. "
                f"Your {persona[:80]}. Price sensitivity: 0.3/1 "
                "(1=very price conscious). "
                "Think critically: Was it worth the price? Did it meet expectations for what you paid? "
                "Be honest — give 1-2 if it was disappointing or overpriced, 3 if it was just okay, "
                "4 if genuinely good value, 5 ONLY if it exceeded expectations. "
                "Highly price-sensitive consumers are harder to impress at higher price points. "
                "Return ONLY valid JSON: {\"rating\": 1-5, \"review\": \"1-2 honest sentences\"}"
            ),
            100,
        )

    # ── Business: _handle_question ────────────────────────────────
    @staticmethod
    def business_qa() -> tuple[str, str, int]:
        return (
            "You are TechZone Electronics, a electronics business. Be helpful and concise. Return ONLY valid JSON.",
            (
                "Customer asks about Samsung 65\" 4K QLED TV: "
                "\"Does this TV support Dolby Vision and what's the response time for gaming?\"\n"
                "FAQs: Q:What is your return policy? A:30-day returns, no questions asked | "
                "Q:Do you offer price matching? A:Yes, we match any competitor's price within 14 days | "
                "Q:What warranty is included? A:1-year manufacturer warranty plus our 90-day satisfaction guarantee\n"
                "Return: {\"answer\": \"concise answer\"}"
            ),
            100,
        )

    # ── Business: _dynamic_pricing ────────────────────────────────
    @staticmethod
    def business_pricing() -> tuple[str, str, int]:
        return (
            (
                "You are the pricing strategist for TechZone Electronics, a electronics business. "
                "Conversion rate: 34% (12/35 queries). "
                "Quality score: 95/100. "
                "Constraints: prices must stay within 75%–130% of base_price. "
                "Return ONLY valid JSON."
            ),
            (
                "Products: ["
                "{\"sku\": \"TECH-TV-001\", \"name\": \"Samsung 65\\\" 4K QLED TV\", \"current_price\": 899.99, \"base_price\": 899.99, \"inventory\": 4, \"avg_rating\": 4.5}, "
                "{\"sku\": \"TECH-LAPTOP-001\", \"name\": \"MacBook Pro 14\\\" M3\", \"current_price\": 1999.00, \"base_price\": 1999.00, \"inventory\": 12, \"avg_rating\": 4.8}, "
                "{\"sku\": \"TECH-PHONE-001\", \"name\": \"iPhone 15 Pro\", \"current_price\": 1099.00, \"base_price\": 1099.00, \"inventory\": 28, \"avg_rating\": null}, "
                "{\"sku\": \"TECH-AUDIO-001\", \"name\": \"Sony WH-1000XM5\", \"current_price\": 349.99, \"base_price\": 349.99, \"inventory\": 7, \"avg_rating\": 4.7}, "
                "{\"sku\": \"TECH-TAB-001\", \"name\": \"iPad Pro 11\\\" M4\", \"current_price\": 1299.00, \"base_price\": 1299.00, \"inventory\": 65, \"avg_rating\": 4.6}]\n"
                "Suggest price adjustments considering inventory levels, ratings, and conversion rate. "
                "Return: {\"adjustments\": [{\"sku\": \"X\", \"new_price\": 0.0, \"reason\": \"brief\"}], "
                "\"strategy\": \"one sentence on overall approach\"}"
            ),
            250,
        )

    # ── Business: _strategic_review ───────────────────────────────
    @staticmethod
    def business_strategy() -> tuple[str, str, int]:
        return (
            (
                "You are the strategic advisor for StyleHub Fashion. "
                "Give a concise, actionable assessment. Return ONLY valid JSON."
            ),
            (
                "Business metrics:\n"
                "- Quality score: 41/100\n"
                "- Quality issues: ['Missing or very short business description', 'No FAQs provided', 'No return policy specified', 'Product \\'Summer Floral Dress\\' has no description']\n"
                "- Conversion rate: 18% (3 orders from 17 queries)\n"
                "- Average customer rating: 2.8\n"
                "- Total revenue: $287.50\n"
                "- Inventory levels: {'STYLE-DRESS-001': 18, 'STYLE-JEANS-001': 22, 'STYLE-TOP-001': 31}\n\n"
                "Return: {\"insight\": \"1-2 sentence assessment\", "
                "\"priority_action\": \"one of: improve_descriptions|add_faqs|adjust_pricing|increase_inventory|maintain_course\", "
                "\"urgency\": \"high|medium|low\"}"
            ),
            160,
        )

    # ── Business: _handle_negotiation_request ─────────────────────
    @staticmethod
    def business_negotiation() -> tuple[str, str, int]:
        return (
            "You are the sales agent for WiredWorld. Make a negotiation decision. Return ONLY valid JSON.",
            (
                "Customer wants to buy 'Samsung 65\" 4K QLED TV' (listed at $849.00). "
                "They prefer $746.12, max $849.00. "
                "Inventory: 11 units. Conversion rate: 29%. "
                "Floor price (don't go below): $696.18. "
                "Return: {\"action\": \"accept\" or \"counter\" or \"decline\", "
                "\"offered_price\": <price if accept/counter>, "
                "\"reason\": \"brief\"}"
            ),
            100,
        )

    @staticmethod
    def sim_mix() -> tuple[str, str, int]:
        """Random sample weighted by live simulation call frequencies."""
        return random.choices(
            population=[
                SimPrompts.consumer_discovery,
                SimPrompts.consumer_consideration,
                SimPrompts.consumer_convert,
                SimPrompts.consumer_review,
                SimPrompts.business_qa,
                SimPrompts.business_pricing,
                SimPrompts.business_strategy,
                SimPrompts.business_negotiation,
            ],
            # Approximate frequencies per tick across all agents:
            #   consumer_discovery  ~10%   consumer_consider ~15%
            #   consumer_convert    ~12%   consumer_review   ~10%
            #   business_qa          ~8%   business_pricing  ~20%
            #   business_strategy   ~10%   business_negotiation ~15%
            weights=[10, 15, 12, 10, 8, 20, 10, 15],
            k=1,
        )[0]()


SCENARIOS: dict[str, callable] = {
    "consumer_discovery":  SimPrompts.consumer_discovery,
    "consumer_consider":   SimPrompts.consumer_consideration,
    "consumer_convert":    SimPrompts.consumer_convert,
    "consumer_review":     SimPrompts.consumer_review,
    "business_qa":         SimPrompts.business_qa,
    "business_pricing":    SimPrompts.business_pricing,
    "business_strategy":   SimPrompts.business_strategy,
    "business_negotiation": SimPrompts.business_negotiation,
    "sim_mix":             SimPrompts.sim_mix,
}


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class CallResult:
    success: bool
    latency_s: float
    scenario: str = "unknown"
    error_type: Optional[str] = None   # "rate_limit" | "timeout" | "parse" | "other"
    error_msg: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    truncated: bool = False            # stop_reason == "max_tokens" → JSON cut off mid-response


@dataclass
class BenchResult:
    provider: str
    model: str
    scenario: str
    concurrency: int
    n_requests: int
    calls: list[CallResult] = field(default_factory=list)

    @property
    def n_success(self) -> int:
        return sum(1 for c in self.calls if c.success)

    @property
    def n_failed(self) -> int:
        return len(self.calls) - self.n_success

    @property
    def success_rate(self) -> float:
        return self.n_success / len(self.calls) if self.calls else 0.0

    @property
    def n_truncated(self) -> int:
        return sum(1 for c in self.calls if c.truncated)

    @property
    def errors_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.calls:
            if c.error_type:
                counts[c.error_type] = counts.get(c.error_type, 0) + 1
        return counts

    @property
    def latencies(self) -> list[float]:
        return [c.latency_s for c in self.calls if c.success]

    @property
    def p50(self) -> Optional[float]:
        ls = sorted(self.latencies)
        return statistics.median(ls) if ls else None

    @property
    def p95(self) -> Optional[float]:
        ls = sorted(self.latencies)
        if not ls:
            return None
        return ls[max(0, int(len(ls) * 0.95) - 1)]

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def summary(self, wall_s: float = 0.0) -> str:
        lines = [
            f"  provider      : {self.provider}",
            f"  model         : {self.model}",
            f"  scenario      : {self.scenario}",
            f"  concurrency   : {self.concurrency}",
            f"  requests      : {self.n_requests}  (success={self.n_success}, failed={self.n_failed})",
            f"  success rate  : {self.success_rate*100:.1f}%",
        ]
        if self.latencies:
            lines += [
                f"  latency p50   : {self.p50:.2f}s",
                f"  latency p95   : {self.p95:.2f}s",
                f"  latency min   : {min(self.latencies):.2f}s",
                f"  latency max   : {max(self.latencies):.2f}s",
            ]
        if self.n_truncated:
            lines.append(
                f"  ⚠️  truncated  : {self.n_truncated}/{self.n_requests} responses hit max_tokens "
                f"— JSON likely cut off, fallback will fire in production"
            )
        if self.errors_by_type:
            lines.append(f"  errors        : {self.errors_by_type}")
        total_tok = self.total_input_tokens + self.total_output_tokens
        if total_tok:
            lines.append(
                f"  tokens        : {self.total_input_tokens} in / "
                f"{self.total_output_tokens} out = {total_tok} total"
            )
            if wall_s > 0:
                lines.append(f"  tok/s         : {total_tok/wall_s:.0f}")
        if wall_s > 0:
            lines.append(
                f"  wall time     : {wall_s:.2f}s  ({self.n_requests/wall_s:.1f} req/s)"
            )
        return "\n".join(lines)


# ── Provider base ─────────────────────────────────────────────────────────────

class Provider(ABC):
    name: str = "base"
    default_model: str = ""

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.default_model

    @abstractmethod
    async def call(self, system: str, user: str, max_tokens: int) -> CallResult:
        """Make one LLM call and return a CallResult."""


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicProvider(Provider):
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    def __init__(self, model: Optional[str] = None):
        super().__init__(model)
        try:
            import anthropic as _a
            key = os.getenv("ANTHROPIC_API_KEY", "")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY env var not set")
            self._client = _a.AsyncAnthropic(api_key=key)
            self._a = _a
        except ImportError:
            raise RuntimeError("pip install anthropic")

    async def call(self, system: str, user: str, max_tokens: int) -> CallResult:
        t0 = time.perf_counter()
        try:
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            lat = time.perf_counter() - t0
            truncated = (resp.stop_reason == "max_tokens")
            return CallResult(
                success=True, latency_s=lat,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                truncated=truncated,
            )
        except self._a.RateLimitError as e:
            return CallResult(success=False, latency_s=time.perf_counter()-t0,
                              error_type="rate_limit", error_msg=str(e)[:120])
        except (asyncio.TimeoutError, self._a.APITimeoutError) as e:
            return CallResult(success=False, latency_s=time.perf_counter()-t0,
                              error_type="timeout", error_msg=str(e)[:120])
        except Exception as e:
            return CallResult(success=False, latency_s=time.perf_counter()-t0,
                              error_type="other", error_msg=str(e)[:120])


# ── Gemini stub ───────────────────────────────────────────────────────────────

class GeminiProvider(Provider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, model=None):
        super().__init__(model)
        raise NotImplementedError("Gemini provider not yet wired — see stub in bench_llm.py")

    async def call(self, system, user, max_tokens):
        raise NotImplementedError


# ── OpenRouter stub ───────────────────────────────────────────────────────────

class OpenRouterProvider(Provider):
    name = "openrouter"
    default_model = "openai/gpt-4o-mini"

    def __init__(self, model=None):
        super().__init__(model)
        try:
            import httpx
            self._base_url = "https://openrouter.ai/api/v1/chat/completions"
            self._key = os.getenv("OPENROUTER_API_KEY", "")
            if not self._key:
                raise RuntimeError("OPENROUTER_API_KEY env var not set")
            self._httpx = httpx
        except ImportError:
            raise RuntimeError("pip install httpx")

    async def call(self, system: str, user: str, max_tokens: int) -> CallResult:
        t0 = time.perf_counter()
        try:
            async with self._httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model, "max_tokens": max_tokens,
                          "messages": [
                              {"role": "system", "content": system},
                              {"role": "user", "content": user},
                          ]},
                )
            lat = time.perf_counter() - t0
            if resp.status_code == 429:
                return CallResult(success=False, latency_s=lat,
                                  error_type="rate_limit", error_msg=resp.text[:120])
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            return CallResult(success=True, latency_s=lat,
                              input_tokens=usage.get("prompt_tokens", 0),
                              output_tokens=usage.get("completion_tokens", 0))
        except asyncio.TimeoutError as e:
            return CallResult(success=False, latency_s=time.perf_counter()-t0,
                              error_type="timeout", error_msg=str(e)[:120])
        except Exception as e:
            return CallResult(success=False, latency_s=time.perf_counter()-t0,
                              error_type="other", error_msg=str(e)[:120])


PROVIDERS: dict[str, type[Provider]] = {
    "anthropic":  AnthropicProvider,
    "gemini":     GeminiProvider,
    "openrouter": OpenRouterProvider,
}


# ── Benchmark runner ──────────────────────────────────────────────────────────

async def run_bench(
    provider: Provider,
    scenario_fn: callable,
    n_requests: int,
    concurrency: int,
    cooldown_s: float = 0.0,
    max_tokens_override: Optional[int] = None,
) -> tuple[BenchResult, float]:
    scenario_name = scenario_fn.__name__
    result = BenchResult(
        provider=provider.name,
        model=provider.model,
        scenario=scenario_name,
        concurrency=concurrency,
        n_requests=n_requests,
    )
    sem = asyncio.Semaphore(concurrency)

    async def one_call(i: int) -> CallResult:
        system, user, max_tokens = scenario_fn()
        if max_tokens_override is not None:
            max_tokens = max_tokens_override
        async with sem:
            r = await provider.call(system, user, max_tokens)
            r.scenario = scenario_name
            if cooldown_s > 0:
                await asyncio.sleep(cooldown_s)
            return r

    t0 = time.perf_counter()
    tasks = [asyncio.create_task(one_call(i)) for i in range(n_requests)]
    for idx, task in enumerate(asyncio.as_completed(tasks), 1):
        call = await task
        result.calls.append(call)
        status = "✓" if call.success else f"✗[{call.error_type}]"
        tok = f" {call.input_tokens}+{call.output_tokens}t" if call.input_tokens else ""
        print(f"  [{idx:>3}/{n_requests}] {status}  {call.latency_s:.2f}s{tok}", end="\r", flush=True)

    wall = time.perf_counter() - t0
    print()
    return result, wall


async def sweep(
    provider: Provider,
    scenario_fn: callable,
    n_requests: int,
    concurrency_levels: list[int],
    cooldown_s: float,
    max_tokens_override: Optional[int] = None,
) -> list[BenchResult]:
    results = []
    tok_note = f"  max_tokens={max_tokens_override} (prod override)" if max_tokens_override else ""
    for c in concurrency_levels:
        print(f"\n{'─'*58}")
        print(f"  concurrency={c}  requests={n_requests}  scenario={scenario_fn.__name__}{tok_note}")
        print(f"{'─'*58}")
        r, wall = await run_bench(provider, scenario_fn, n_requests, c, cooldown_s, max_tokens_override)
        print(r.summary(wall_s=wall))
        results.append(r)
    return results


def print_comparison(results: list[BenchResult]):
    if len(results) < 2:
        return
    print(f"\n{'═'*66}")
    print("  COMPARISON ACROSS CONCURRENCY LEVELS")
    print(f"{'═'*66}")
    print(f"  {'conc':>4}  {'ok%':>5}  {'trunc':>5}  {'p50':>6}  {'p95':>6}  "
          f"{'req/s':>5}  {'tok/s':>6}  errors")
    print(f"  {'─'*4}  {'─'*5}  {'─'*5}  {'─'*6}  {'─'*6}  {'─'*5}  {'─'*6}  {'─'*20}")

    for r in results:
        errs = ", ".join(f"{k}:{v}" for k, v in r.errors_by_type.items()) or "—"
        p50 = f"{r.p50:.2f}s" if r.p50 else "n/a"
        p95 = f"{r.p95:.2f}s" if r.p95 else "n/a"
        trunc = f"{r.n_truncated}" if r.n_truncated else "—"
        total_tok = r.total_input_tokens + r.total_output_tokens
        # Approximate wall from latency distribution
        if r.latencies:
            approx_wall = sum(sorted(r.latencies, reverse=True)[:r.concurrency]) + \
                          (r.n_requests / r.concurrency - 1) * statistics.median(r.latencies)
            approx_wall = max(approx_wall, max(r.latencies))
        else:
            approx_wall = 1.0
        rps = f"{r.n_requests/approx_wall:.1f}" if approx_wall else "n/a"
        tps = f"{total_tok/approx_wall:.0f}" if (total_tok and approx_wall) else "n/a"
        print(f"  {r.concurrency:>4}  {r.success_rate*100:>4.0f}%  {trunc:>5}  {p50:>6}  {p95:>6}  "
              f"{rps:>5}  {tps:>6}  {errs}")

    print()
    best = max(
        (r for r in results if r.success_rate >= 0.95),
        key=lambda r: r.concurrency,
        default=None,
    )
    if best:
        print(f"  ✅ Recommended semaphore limit: {best.concurrency}  "
              f"(highest concurrency with ≥95% success rate)")
    else:
        print("  ⚠️  No concurrency level achieved ≥95% success — consider adding retry + backoff")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Benchmark LLM concurrency with real simulation prompts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--provider", default="anthropic", choices=list(PROVIDERS),
                   help="LLM provider (default: anthropic)")
    p.add_argument("--model", default=None,
                   help="Override model name")
    p.add_argument("--scenario", default="sim_mix", choices=list(SCENARIOS),
                   help="Prompt scenario to run (default: sim_mix)")
    p.add_argument("--requests", type=int, default=30,
                   help="Total requests per concurrency level (default: 30)")
    p.add_argument("--concurrency", type=int, nargs="+", default=[1, 3, 5, 10, 15, 20],
                   help="Concurrency levels to sweep (default: 1 3 5 10 15 20)")
    p.add_argument("--cooldown", type=float, default=0.0,
                   help="Sleep inside semaphore after each call, seconds (default: 0)")
    p.add_argument("--max-tokens", type=int, default=None, dest="max_tokens",
                   help="Override per-scenario max_tokens (e.g. 256 to match production base.py)")
    p.add_argument("--list-scenarios", action="store_true",
                   help="Print available scenarios and exit")
    p.add_argument("--list-providers", action="store_true",
                   help="Print available providers and exit")
    return p.parse_args()


async def main():
    args = parse_args()

    if args.list_scenarios:
        print("Available scenarios:")
        for name in SCENARIOS:
            print(f"  {name}")
        return

    if args.list_providers:
        print("Available providers:")
        for name, cls in PROVIDERS.items():
            print(f"  {name:<14} default model: {cls.default_model}")
        return

    cls = PROVIDERS[args.provider]
    try:
        provider = cls(model=args.model)
    except (NotImplementedError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    scenario_fn = SCENARIOS[args.scenario]
    print(f"\n⚡ bench_llm  provider={provider.name}/{provider.model}")
    print(f"   scenario={args.scenario}  concurrency={args.concurrency}  {args.requests} req each")

    results = await sweep(provider, scenario_fn, args.requests, args.concurrency,
                          args.cooldown, args.max_tokens)
    print_comparison(results)


if __name__ == "__main__":
    asyncio.run(main())
