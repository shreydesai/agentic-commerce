"""
simulation/stats.py — Module-level singletons for infrastructure telemetry.

Accumulated across all agents during a simulation run. Reset by the engine
on each fresh start. Exposed via /api/state under the "infra" key.
"""

from __future__ import annotations
import time


class LLMStats:
    """Tracks every call_llm invocation across all agents."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.total_calls: int = 0
        self.successes: int = 0
        self.failures: int = 0
        self.truncations: int = 0          # stop_reason == max_tokens
        self._total_latency_ms: float = 0.0
        self.errors_by_type: dict[str, int] = {}  # rate_limit | timeout | parse | other

    def record(
        self,
        *,
        success: bool,
        latency_ms: float,
        truncated: bool = False,
        error_type: str | None = None,
    ):
        self.total_calls += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
            key = error_type or "other"
            self.errors_by_type[key] = self.errors_by_type.get(key, 0) + 1
        if truncated:
            self.truncations += 1
        self._total_latency_ms += latency_ms

    def to_dict(self) -> dict:
        n = max(self.total_calls, 1)
        ns = max(self.successes, 1)
        return {
            "total_calls": self.total_calls,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.successes / n, 3),
            "truncations": self.truncations,
            "truncation_rate": round(self.truncations / ns, 3),
            "avg_latency_ms": round(self._total_latency_ms / n, 0),
            "errors_by_type": dict(self.errors_by_type),
        }


class MessageStats:
    """Tracks every send_message call across all agents."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.total: int = 0
        self.by_type: dict[str, int] = {}           # product_query, place_order, …
        self.consumer_to_business: int = 0
        self.business_to_consumer: int = 0
        self.business_to_business: int = 0          # B2B supply chain messages

    def record(self, from_type: str, to_type: str, message_type: str):
        self.total += 1
        self.by_type[message_type] = self.by_type.get(message_type, 0) + 1
        pair = (from_type, to_type)
        if pair == ("consumer", "business"):
            self.consumer_to_business += 1
        elif pair == ("business", "consumer"):
            self.business_to_consumer += 1
        elif pair == ("business", "business"):
            self.business_to_business += 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "consumer_to_business": self.consumer_to_business,
            "business_to_consumer": self.business_to_consumer,
            "business_to_business": self.business_to_business,
            "by_type": dict(
                sorted(self.by_type.items(), key=lambda kv: kv[1], reverse=True)
            ),
        }


# Module-level singletons — imported by agents/base.py
llm_stats = LLMStats()
message_stats = MessageStats()
