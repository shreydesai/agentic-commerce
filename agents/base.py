import asyncio
import json
import time
from typing import Optional
import anthropic
from config import ANTHROPIC_API_KEY, LLM_MODEL
from simulation.events import SimEvent
from simulation.stats import llm_stats, message_stats
from acp.models import AgentMessage


class BaseAgent:
    def __init__(self, agent_id: str, name: str, agent_type: str, event_bus, message_bus: dict):
        self.agent_id = agent_id
        self.name = name
        self.agent_type = agent_type
        self.event_bus = event_bus
        self.message_bus = message_bus
        self.message_bus[agent_id] = asyncio.Queue()
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.active = True

    async def emit_event(
        self,
        event_type: str,
        data: dict,
        message: str = "",
        transaction_id: Optional[str] = None,
        from_agent_id: Optional[str] = None,
        to_agent_id: Optional[str] = None,
    ):
        event = SimEvent(
            event_type=event_type,
            agent_id=self.agent_id,
            agent_name=self.name,
            agent_type=self.agent_type,
            from_agent_id=from_agent_id or self.agent_id,
            to_agent_id=to_agent_id,
            transaction_id=transaction_id,
            data=data,
            message=message,
        )
        await self.event_bus.put(event)

    async def send_message(
        self,
        to_agent_id: str,
        message_type: str,
        content: dict,
        transaction_id: Optional[str] = None,
        emit_network: bool = True,
    ):
        if to_agent_id not in self.message_bus:
            return None
        # Infer recipient type from agent_id prefix for message stats
        to_type = "consumer" if to_agent_id.startswith("consumer") else "business"
        message_stats.record(self.agent_type, to_type, message_type)
        msg = AgentMessage(
            from_agent_id=self.agent_id,
            to_agent_id=to_agent_id,
            message_type=message_type,
            content=content,
        )
        await self.message_bus[to_agent_id].put(msg)

        # Always log the full ACP message content (message inspector / protocol view)
        await self.emit_event(
            "acp_message",
            {"message_type": message_type, "content": content},
            f"{self.name} → {to_agent_id}: [{message_type}]",
            transaction_id=transaction_id,
            from_agent_id=self.agent_id,
            to_agent_id=to_agent_id,
        )

        # Emit network visualization event for key messages
        if emit_network and message_type in {
            "product_query", "place_order", "question", "supply_order",
            "product_response", "order_confirmation", "question_answer",
            "supply_confirmation", "review", "order_rejected",
        }:
            await self.emit_event(
                "network_message",
                {"message_type": message_type},
                "",
                transaction_id=transaction_id,
                from_agent_id=self.agent_id,
                to_agent_id=to_agent_id,
            )
        return msg

    async def receive_message(self, timeout: float = 5.0):
        try:
            return await asyncio.wait_for(self.message_bus[self.agent_id].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def call_llm(self, system: str, user: str, max_tokens: int = 256) -> dict:
        t0 = time.perf_counter()
        try:
            response = await self.client.messages.create(
                model=LLM_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            truncated = (response.stop_reason == "max_tokens")
            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]
            result = json.loads(text)
            llm_stats.record(success=True, latency_ms=latency_ms, truncated=truncated)
            return result
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            err = str(e)
            error_type = (
                "rate_limit" if "rate_limit" in err.lower() or "429" in err else
                "timeout"    if "timeout"    in err.lower() else
                "parse"      if isinstance(e, (json.JSONDecodeError, ValueError)) else
                "other"
            )
            llm_stats.record(success=False, latency_ms=latency_ms, error_type=error_type)
            return {"error": err}

    async def run(self):
        raise NotImplementedError

    def stop(self):
        self.active = False
