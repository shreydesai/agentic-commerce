import asyncio
import json
from typing import Optional
import anthropic
from config import ANTHROPIC_API_KEY, LLM_MODEL
from simulation.events import SimEvent
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
        msg = AgentMessage(
            from_agent_id=self.agent_id,
            to_agent_id=to_agent_id,
            message_type=message_type,
            content=content,
        )
        await self.message_bus[to_agent_id].put(msg)

        # Emit network visualization event for key messages
        if emit_network and message_type in {
            "product_query", "place_order", "question", "supply_order",
            "product_response", "order_confirmation", "question_answer",
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

    async def call_llm(self, system: str, user: str) -> dict:
        try:
            response = await self.client.messages.create(
                model=LLM_MODEL,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    async def run(self):
        raise NotImplementedError

    def stop(self):
        self.active = False
