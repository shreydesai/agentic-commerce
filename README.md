# Agentic Commerce Simulator

A full end-to-end agentic commerce prototype featuring LLM-powered consumer and business agents, the Agentic Commerce Protocol (ACP), B2C/B2B supply chain relationships, a real-time god-view dashboard with network visualization, and SQLite persistence.

## Features

- **12 business agents** — 5 high-quality B2C merchants, 3 intentionally imperfect B2C merchants, 4 B2B suppliers
- **5 consumer agents** — rich demographic and behavioral profiles (price sensitivity, brand loyalty, impulse tendency, research depth)
- **Quality score system** — each business is scored 0–100 on catalog completeness; imperfect businesses (missing prices, sparse descriptions, no FAQs) lose real transactions because the score is injected into consumer LLM prompts
- **Network visualization** — live animated canvas showing communication paths between agents with per-message-type color coding and 4s TTL fade
- **SQLite persistence** — save/load full simulation state; startup modal offers "Load Previous" or "Start Fresh"
- **Transaction tracking** — every shopping session has a UUID propagated through all events; grouped transaction view with expandable funnel steps
- **Activity feed filters** — All / Transactions / Purchases / Supply Chain / Reviews
- **Consumer detail view** (`/consumer/{id}`) — demographics, behavioral trait bars, funnel stage, purchase history
- **Business detail view** (`/business/{id}`) — animated quality score ring, catalog with issue highlighting, orders, company info
- **56 pytest tests** covering agents, DB persistence, simulation engine, and ACP models

## Architecture

```
agentic-commerce/
├── acp/            # ACP message models (Product, AgentMessage, Transaction)
├── agents/         # BaseAgent, ConsumerAgent, BusinessAgent (unified B2C + B2B)
├── simulation/     # SimulationEngine, SimEvent, seed data
├── api/            # FastAPI backend + WebSocket manager
├── db/             # SQLite schema, persistence helpers
├── tests/          # pytest test suite (56 tests)
└── ui/             # God-view dashboard + consumer/business detail pages
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for component diagrams and data flow.

## Agents

### Consumer Agents (5)

| Name | Age | Occupation | Budget | Key trait |
|---|---|---|---|---|
| Alex Chen | 28 | Software Engineer | $2,000 | research_depth=0.90 |
| Sarah Park | 34 | Marketing Manager | $600 | brand_loyalty=0.70 |
| Mike Johnson | 45 | Truck Driver | $300 | price_sensitivity=0.90 |
| Emma Davis | 22 | Design Student | $400 | impulse_tendency=0.80 |
| Tom Wilson | 38 | IT Manager | $1,500 | research_depth=0.80 |

Each traverses the full shopping funnel:
`IDLE → DISCOVERING → CONSIDERING → CONVERTING → POST_PURCHASE → IDLE`

### Business Agents (12)

**B2C — High Quality (~88–95 score):**
TechZone Electronics, StyleHub Fashion, FreshMart Grocery, HomeNest Furnishings, GameVault

**B2C — Imperfect (~45–61 score):**
PixelDrop Tech (products with price=0, no FAQs), VagueFashion (sparse descriptions), QuickByte Foods (minimal policies)

**B2B Suppliers:**
ComponentsCorp (electronics), FabricWorld (fashion), MaterialsHub (home), FreshFarmSupply (grocery)

### Agentic Commerce Protocol (ACP)

All agent-to-agent communication uses a typed message bus:

| Message | Direction |
|---|---|
| `product_query` / `product_response` | Consumer → B2C merchant |
| `question` / `question_answer` | Consumer ↔ merchant |
| `place_order` / `order_confirmation` / `order_rejected` | Consumer → merchant |
| `review` | Consumer → merchant |
| `supply_order` / `supply_confirmation` | B2C merchant ↔ B2B supplier |

## Setup

```bash
cd agentic-commerce
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

python run.py
# Open http://localhost:8000
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## UI

| View | URL | Description |
|---|---|---|
| God view | `/` | Network canvas, activity feed with filters, all agent states |
| Consumer detail | `/consumer/{id}` | Demographics, trait bars, funnel, purchase history |
| Business detail | `/business/{id}` | Quality ring, catalog, orders, company info |

On startup, a modal checks for a saved simulation state and offers to load it or start fresh.

## LLM Model

Uses `claude-haiku-4-5-20251001` for all agent LLM calls (cheapest Anthropic model). Each consumer makes ~4–5 LLM calls per shopping cycle (shortlisting, purchase decision, review generation).

**Cost estimate:** ~$0.05–0.10/hour of simulation with default settings.

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — Component diagram, data flows, config reference
- [FUTURE_IDEAS.md](FUTURE_IDEAS.md) — Vision for agentic commerce in 2050, grounded in 2025–2026 research (real protocols, live deployments, analyst forecasts, academic collusion research)
