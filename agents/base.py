import asyncio
import json
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

    async def emit_event(self, event_type: str, data: dict, message: str = ""):
        event = SimEvent(
            event_type=event_type,
            agent_id=self.agent_id,
            agent_name=self.name,
            agent_type=self.agent_type,
            data=data,
            message=message,
        )
        await self.event_bus.put(event)

    async def send_message(self, to_agent_id: str, message_type: str, content: dict):
        if to_agent_id in self.message_bus:
            msg = AgentMessage(
                from_agent_id=self.agent_id,
                to_agent_id=to_agent_id,
                message_type=message_type,
                content=content,
            )
            await self.message_bus[to_agent_id].put(msg)
            return msg
        return None

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
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    async def run(self):
        raise NotImplementedError

    def stop(self):
        self.active = False
