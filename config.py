import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-haiku-4-5-20251001"
CONSUMER_TICK_SECONDS = 8
LOW_INVENTORY_THRESHOLD = 10
SIMULATION_SPEED_FACTOR: float = float(os.getenv("SIMULATION_SPEED_FACTOR", "1.0"))
DB_PATH = os.getenv("DB_PATH", "simulation.db")
