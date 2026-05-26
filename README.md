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
│  IDLE              │  discovery_ping  │  B2C:              │
│  DISCOVERING       │  discovery_pong  │  handle queries    │
│  CONSIDERING       │  product_query   │  fulfill orders    │
│  CONVERTING        │  product_resp    │  negotiate prices  │
│  AWAITING_DELIVERY │  negotiation_*   │  delivery notices  │
│  POST_PURCHASE     │  place_order     │  strategic review  │
│                    │  order_confirm   │                    │
│  LLM calls:        │  delivery_notice │  B2B:              │
│  shortlist         │  review          │  fulfill restocks  │
│  decide            │  supply_order    │  delay simulation  │
│  negotiate         │  supply_confirm  │                    │
│  review            │                 │  LLM calls:        │
│                    │                 │  dynamic pricing   │
│  traits evolve     │                 │  negotiation       │
│  after purchase    │                 │  strategic review  │
└────────────────────┘                 │  poor review resp  │
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

**10 Consumer Agents** — each has a full demographic profile plus behavioral traits (all 0–1):

| Name | Budget | price_sensitivity | brand_loyalty | impulse | research |
|---|---|---|---|---|---|
| Alex Chen | $2,000 | 0.20 | 0.80 | 0.30 | 0.90 |
| Sarah Park | $600 | 0.55 | 0.70 | 0.45 | 0.60 |
| Mike Johnson | $300 | 0.90 | 0.30 | 0.20 | 0.70 |
| Emma Davis | $400 | 0.40 | 0.50 | 0.80 | 0.35 |
| Tom Wilson | $1,500 | 0.35 | 0.65 | 0.25 | 0.80 |
| + 5 more | … | … | … | … | … |

Traits **evolve after each purchase**: good reviews increase brand loyalty, bad ones raise price sensitivity and research depth. High `research_depth` consumers apply a stricter merchant quality gate during discovery (up to 75/100).

**17 Business Agents:**

| Type | Count | Examples | Avg Quality |
|---|---|---|---|
| B2C High-Quality | 8 | TechZone, StyleHub, FreshMart, HomeNest, GameVault | 88–95 |
| B2C Imperfect | 5 | PixelDrop Tech, VagueFashion, QuickByte Foods | 45–61 |
| B2B Suppliers | 4 | ComponentsCorp, FabricWorld, MaterialsHub, FreshFarmSupply | — |

Imperfect merchants have real catalog flaws (missing prices, no FAQs, sparse descriptions) — those flaws get injected into consumer LLM prompts and cause measurable lost sales.

### ACP Message Protocol

All agent communication goes through a typed async message bus. 18 message types across 4 flows — LLM is invoked only where judgment is required; everything else is rule-based and instant.

#### Consumer ↔ B2C Business

**Phase 1 — Discovery** (attention economy gate)
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `discovery_ping` | Consumer → B2C | ❌ | Consumer asks "can you serve me?" — sent only to merchants above the quality threshold (35–75/100, scaled by `research_depth`) |
| `discovery_pong` | B2C → Consumer | ❌ | Merchant responds with `can_serve` flag, `quality_tier`, and vertical — instant, no LLM; gates whether a product query is sent |

**Phase 2 — Product Search**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `product_query` | Consumer → B2C | ❌ | Full catalog search — sent only to merchants who returned `can_serve: true` |
| `product_response` | B2C → Consumer | ❌ | Matching products with SKU, price, quality_score |

**Phase 3 — Consideration (optional)**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `question` | Consumer → B2C | ❌ | Product-specific question; fired by high `research_depth` consumers ~50% of the time |
| `question_answer` | B2C → Consumer | ✅ | LLM answer using FAQs as context |

**Phase 4 — Negotiation (optional, up to 3 rounds)**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `negotiation_request` | Consumer → B2C | ❌ | Round 1 bid at 88% of asking; triggered by `price_sensitivity > 0.52` + `research_depth > 0.35` |
| `negotiation_bid` | Consumer → B2C | ❌ | Rounds 2–3: consumer splits-the-difference if gap > 3% and rounds remain |
| `counter_offer` | B2C → Consumer | ✅ | LLM accept/counter/decline; floor at 82% of base price; forced to resolve on `is_final` round |
| `negotiation_accept` | Consumer → B2C | ❌ | Consumer accepts — `place_order` follows at agreed price |
| `negotiation_decline` | B2C → Consumer | ✅ | Price is firm |

**Phase 5 — Conversion**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `place_order` | Consumer → B2C | ❌ | Order at confirmed price (negotiated or full) |
| `order_confirmation` | B2C → Consumer | ❌ | Inventory decremented; delivery notice task scheduled |
| `order_rejected` | B2C → Consumer | ❌ | Out of stock |

**Phase 6 — Delivery**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `delivery_notice` | B2C → Consumer | ❌ | Sent 3–8s after order confirmation (speed-factor scaled); consumer advances from `AWAITING_DELIVERY` to `POST_PURCHASE` |

**Phase 7 — Review**
| Message | Direction | LLM? | Description |
|---|---|---|---|
| `review` | Consumer → B2C | ✅ | Quality-informed rating + text; triggers catalog improvement if SKU avg drops below 3.2 |

#### B2C ↔ B2B Supplier

| Message | Direction | LLM? | Description |
|---|---|---|---|
| `supply_order` | B2C → B2B | ❌ | Restock request (25 units) when inventory ≤ threshold; `supply_txn_id` threaded for tracing |
| `supply_confirmation` | B2B → B2C | ❌ | Fulfillment after simulated 2–5s delay; inventory credited immediately |

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
python3 -m pytest tests/ -v
# 134+ tests across: agents, ACP, DB persistence, engine, scenarios, e2e flows, API
# Unit + E2E suite runs in ~10s (asyncio.sleep mocked to instant yield in tests)
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
| v0.3 | Discovery quality gate + `discovery_ping/pong` (attention economy), `AWAITING_DELIVERY` state + `delivery_notice`, multi-round negotiation (3 rounds), infrastructure analytics (LLM reliability, ACP message flow), review quality signal, merchant blocking |

**Next:** multi-session preference learning, collusion detection, multi-tier supply chain, configurable autonomy levels, warranty/return flows.
