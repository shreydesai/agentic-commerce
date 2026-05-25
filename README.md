# Agentic Commerce Simulator

A living simulation of the agentic commerce economy — LLM-powered agents buying, selling, and negotiating with each other in real time, grounded in the real protocols, deployments, and research shaping commerce in 2025–2026.

> *"AI-attributed orders grew 11× between Jan 2025 and Jan 2026. AI-referred shoppers converted 31% higher with revenue per visit up 254% YoY."* — Adobe Holiday 2025 data
>
> *"$3T–$5T in global retail redirected through agents by 2030."* — McKinsey
>
> *"$15T in B2B spend through agent exchanges by 2028."* — Gartner

---

## What

A fully autonomous multi-agent marketplace where:

- **Consumer agents** with distinct personalities and budgets browse, shortlist, negotiate prices, place orders, and write reviews — driven by Claude Haiku with no human in the loop
- **B2C merchant agents** respond to queries, fulfill orders, run LLM-driven pricing strategy, respond to bad reviews, and negotiate discounts in real time
- **B2B supplier agents** receive restock orders, simulate fulfillment delays, and confirm shipments — closing the supply chain loop
- A **god-view dashboard** shows every agent, every message, and every transaction live — with an analytics panel, scenario engine, and speed control

The simulation is designed to incrementally approach a [2050 north star](FUTURE_IDEAS.md): a fully autonomous agent economy with programmable wallets, multi-party negotiation, emergent market dynamics, and decentralized trust infrastructure.

---

## Why

Agentic commerce is happening now:

- **ChatGPT Instant Checkout** (Sept 2025): real purchases via Stripe ACP — Etsy live at launch, 1M+ Shopify merchants following
- **Amazon Buy for Me** (Mar 2026): agents navigate third-party sites, fill checkout forms, pay with stored credentials — 100M+ indexed products
- **Stripe Machine Payments Protocol** (Mar 2026): a 402 HTTP flow where agents pay and receive resources in a single request-response cycle
- **Visa Trusted Agent Protocol**, **Mastercard Agent Pay**, **Coinbase Agentic Wallets** — three competing agent identity frameworks, all live

This simulator lets you explore the dynamics of this economy in a controlled environment: What happens when consumer agents negotiate? When a supply shock hits all B2B inventory? When merchants with imperfect catalogs lose business to better-prepared competitors? When price wars break out?

---

## How

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Browser (God View)                  │
│  Network Canvas · Activity Feed · Analytics · Scenarios│
└────────────────────┬───────────────────────────────────┘
                     │ WebSocket
┌────────────────────▼───────────────────────────────────┐
│              FastAPI Server  (api/app.py)               │
│  /api/start  /api/stop  /api/state  /api/transactions  │
│  /api/scenario  /api/speed  /api/messages  WS /ws      │
└────────────────────┬───────────────────────────────────┘
                     │ asyncio
┌────────────────────▼───────────────────────────────────┐
│           SimulationEngine  (simulation/engine.py)      │
│  event_bus: asyncio.Queue → WebSocket broadcast        │
│  message_bus: dict[agent_id → asyncio.Queue]           │
│  speed_factor · active_scenarios · scenario originals  │
└──────┬─────────────────────────────────────┬───────────┘
       │                                     │
┌──────▼──────────┐                 ┌────────▼───────────┐
│  ConsumerAgent  │   ACP messages  │   BusinessAgent    │
│  consumer.py    │ ◄─────────────► │   business.py      │
│                 │                 │                    │
│  IDLE           │  product_query  │  B2C:              │
│  DISCOVERING    │  product_resp   │  handle queries    │
│  CONSIDERING    │  negotiation_*  │  fulfill orders    │
│  CONVERTING     │  place_order    │  negotiate prices  │
│  POST_PURCHASE  │  order_confirm  │  strategic review  │
│                 │  review         │                    │
│  LLM calls:     │  supply_order   │  B2B:              │
│  shortlist      │  supply_confirm │  fulfill restocks  │
│  decide         │                 │  delay simulation  │
│  negotiate      │                 │                    │
│  review         │                 │  LLM calls:        │
│                 │                 │  dynamic pricing   │
│  traits evolve  │                 │  negotiation       │
│  after purchase │                 │  strategic review  │
└─────────────────┘                 │  poor review resp  │
                                    └────────────────────┘
```

### File Structure

```
agentic-commerce/
├── acp/                    # ACP message models (AgentMessage, Transaction)
├── agents/
│   ├── base.py             # BaseAgent: send/receive messages, emit events, call LLM
│   ├── consumer.py         # ConsumerAgent: purchase funnel, negotiation, trait evolution
│   └── business.py         # BusinessAgent: B2C+B2B, pricing, negotiation, strategy
├── simulation/
│   ├── engine.py           # Orchestration, scenario engine, speed control
│   ├── events.py           # SimEvent, event colors, filter categories
│   └── seed_data.py        # Pre-defined agents for reproducibility
├── api/app.py              # FastAPI endpoints + WebSocket manager
├── db/                     # SQLite schema + persistence helpers
├── tests/                  # 247 pytest tests
└── ui/                     # God-view dashboard, detail views, analytics
```

### Agents

**5 Consumer Agents** — each has a full demographic profile plus behavioral traits (all 0–1):

| Name | Budget | price_sensitivity | brand_loyalty | impulse | research |
|---|---|---|---|---|---|
| Alex Chen | $2,000 | 0.20 | 0.80 | 0.30 | 0.90 |
| Sarah Park | $600 | 0.55 | 0.70 | 0.45 | 0.60 |
| Mike Johnson | $300 | 0.90 | 0.30 | 0.20 | 0.70 |
| Emma Davis | $400 | 0.40 | 0.50 | 0.80 | 0.35 |
| Tom Wilson | $1,500 | 0.35 | 0.65 | 0.25 | 0.80 |

Traits **evolve after each purchase**: good reviews increase brand loyalty, bad ones raise price sensitivity and research depth.

**12 Business Agents:**

| Type | Count | Examples | Avg Quality |
|---|---|---|---|
| B2C High-Quality | 5 | TechZone, StyleHub, FreshMart, HomeNest, GameVault | 88–95 |
| B2C Imperfect | 3 | PixelDrop Tech, VagueFashion, QuickByte Foods | 45–61 |
| B2B Suppliers | 4 | ComponentsCorp, FabricWorld, MaterialsHub, FreshFarmSupply | — |

Imperfect merchants have real catalog flaws (missing prices, no FAQs, sparse descriptions) — those flaws get injected into consumer LLM prompts and cause measurable lost sales.

### ACP Message Protocol

All agent communication goes through a typed async message bus:

| Message Type | Direction | Description |
|---|---|---|
| `product_query` | Consumer → B2C | Discover products by category + max price |
| `product_response` | B2C → Consumer | Catalog search results with quality scores |
| `negotiation_request` | Consumer → B2C | Request discount (88% of asking, triggered by high price_sensitivity + research_depth) |
| `counter_offer` | B2C → Consumer | LLM-driven response, floor at 82% of base price |
| `negotiation_accept` | Consumer → B2C | Accept counter; `place_order` follows at agreed price |
| `negotiation_decline` | B2C → Consumer | Price is firm |
| `place_order` | Consumer → B2C | Order at confirmed price |
| `order_confirmation` | B2C → Consumer | Fulfillment confirmation |
| `review` | Consumer → B2C | Rating + text; triggers catalog improvement if avg < 3.2 |
| `supply_order` | B2C → B2B | Restock request when inventory ≤ threshold |
| `supply_confirmation` | B2B → B2C | Fulfillment after simulated delay |

### Key Features

**Business Intelligence (LLM-driven):**
- Dynamic pricing every 30 ticks — Claude adjusts prices from inventory, conversion rate, and ratings; clamped to 75–130% of base price
- Strategic review every 50 ticks — LLM market assessment emitted as `strategy_update` events
- Poor review response — when SKU avg drops below 3.2, LLM rewrites the product description
- Negotiation handling — LLM decides accept/counter/decline; fallback rule-based logic

**Consumer Intelligence:**
- Purchase history (last 5 sessions) fed back into shortlisting LLM prompt
- Per-merchant satisfaction history informs conversion decisions
- Price negotiation: consumers with price_sensitivity > 0.52 and research_depth > 0.35 attempt to negotiate
- Trait evolution after each purchase (±0.01–0.03, clamped to [0, 1])

**Analytics Dashboard:**
- Revenue sparkline (last 60 purchase events, pure SVG — no external libraries)
- Transaction funnel breakdown, merchant leaderboard with conversion rates
- Consumer spending bars, AI strategy notes

**Scenario Engine** (injectable mid-simulation):

| Scenario | Effect |
|---|---|
| 📉 Recession | Consumer budgets −40%, price sensitivity +0.20 |
| 🛍️ Black Friday | Budgets +30%, impulse tendency +0.25 |
| 🏭 Supply Shock | All B2B inventory → 10% |
| 💥 Price War | All B2C prices −20% |
| ⭐ Quality Boost | Imperfect merchants get FAQs, policies, fixed prices |
| 🔄 Reset | Restore all original values |

**Speed Control:** 0.25×–5× multiplier applied live to all agent sleep loops — no restart needed.

---

## Setup

```bash
git clone https://github.com/shreydesai/agentic-commerce
cd agentic-commerce
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY

python run.py
# → http://localhost:8000
```

### Tests

```bash
python -m pytest tests/ -v
# 247 tests across: agents, ACP, DB persistence, engine, scenarios, e2e flows, API
```

### Cost

Uses `claude-haiku-4-5-20251001` for all LLM calls. Estimated **~$0.05–0.15/hour** at default speed.

---

## UI

| View | URL | What you see |
|---|---|---|
| God View | `/` | 3-column: consumers · network canvas + feed · businesses |
| Analytics | `/ → 📊 Analytics` | Revenue sparkline, leaderboard, funnel, strategy notes |
| Scenarios | `/ → ⚡ Scenarios` | 6 market scenarios + speed slider |
| Consumer detail | `/consumer/{id}` | Demographics, trait bars, funnel stage, purchase history |
| Business detail | `/business/{id}` | Quality ring, catalog, orders, strategy notes |

On startup, a modal checks for a saved state and offers Load Previous / Start Fresh.

---

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — Component diagram, data flows, full config reference
- [FUTURE_IDEAS.md](FUTURE_IDEAS.md) — Grounded 2050 vision: 12 pillars from agent identity to emergent market dynamics, with changelog of what's been shipped

---

## Roadmap (toward 2050)

The [FUTURE_IDEAS.md](FUTURE_IDEAS.md) document tracks a 12-pillar north star. Shipped so far:

| Version | Feature |
|---|---|
| v0.1 | ACP message protocol, LLM consumer funnel, quality scoring, B2B supply chain, SQLite persistence |
| v0.2 | Price negotiation, consumer memory + trait evolution, LLM business intelligence, analytics dashboard, scenario engine, speed control |

**Next:** multi-session preference learning, collusion detection, multi-tier supply chain, configurable autonomy levels, warranty/return flows.
