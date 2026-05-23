import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-haiku-4-5-20251001"
CONSUMER_TICK_SECONDS = 12
LOW_INVENTORY_THRESHOLD = 5
