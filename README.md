# Agentic Commerce Simulator

A full end-to-end agentic commerce prototype featuring LLM-powered consumer and business agents, the Agentic Commerce Protocol (ACP), B2B supplier relationships, and a real-time god-view dashboard.

## Architecture

```
agentic-commerce/
├── acp/            # Agentic Commerce Protocol models (catalogs, orders, messages)
├── agents/         # Agent implementations (consumer, merchant, supplier)
├── simulation/     # Engine, event system, seed data
├── api/            # FastAPI backend + WebSocket manager
└── ui/             # God-view dashboard (HTML/CSS/JS)
```

### Agents

**Consumer Agents (5)** — Each has a persona, preferences, and budget. They traverse the full shopping funnel:
- `IDLE → DISCOVERING` — LLM picks what to search for
- `DISCOVERING → CONSIDERING` — Queries merchants via ACP, collects product listings
- `CONSIDERING → CONVERTING` — LLM evaluates options, may ask merchant a clarifying question
- `CONVERTING → POST_PURCHASE` — LLM makes final buy/pass decision, processes checkout
- `POST_PURCHASE → IDLE` — LLM writes a product review, cycle repeats

**Merchant Agents (5)** — Each represents a business with a product catalog, FAQs, and a supplier:
- Responds to product queries (catalog search)
- Answers customer questions (LLM-generated answers using FAQs)
- Processes orders, tracks revenue and inventory
- Automatically reorders from supplier when inventory is low

**Supplier Agents (3)** — B2B wholesale suppliers:
- Receive restock orders from merchants
- Simulate supply chain delay (2–5 seconds)
- Confirm fulfillment back to merchants

### Verticals
| Merchant | Vertical | Supplier |
|---|---|---|
| TechZone Electronics | electronics | ComponentsCorp |
| StyleHub Fashion | fashion | FabricWorld |
| FreshMart Grocery | grocery | *(none)* |
| HomeNest Furnishings | home | MaterialsHub |
| GameVault | gaming | ComponentsCorp |

### Agentic Commerce Protocol (ACP)
All agent-to-agent communication uses a typed message bus:
- `product_query` / `product_response` — catalog discovery
- `question` / `question_answer` — pre-purchase Q&A
- `place_order` / `order_confirmation` / `order_rejected` — checkout
- `review` — post-purchase feedback
- `supply_order` / `supply_confirmation` — B2B restocking

### LLM Model
Uses `claude-haiku-4-5-20251001` (cheapest Anthropic model) with short prompts (~300 input tokens, ~150 output tokens per call). Each consumer makes ~4–5 LLM calls per full shopping cycle.

## Setup

```bash
cd agentic-commerce
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

python run.py
# Open http://localhost:8000
```

## UI Controls

- **▶ Start** — Launches all agents; commerce begins
- **⏹ Stop** — Gracefully stops all agents
- **God View** — Live activity feed, consumer funnel states, merchant revenue/inventory, supplier fulfillment

## Cost Estimate

With default settings (12s consumer tick, 5 consumers):
- ~4–5 LLM calls per shopping cycle (~60s cycle)
- Haiku pricing: ~$0.001–0.002 per call
- Estimated: **< $0.10/hour** of simulation
