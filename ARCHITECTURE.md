# Architecture

This document describes the major technical components of the agentic commerce simulation and how they interact.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (UI)                                │
│                                                                     │
│  ┌───────────┐  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │ index.html│  │  consumer.html       │  │   business.html      │ │
│  │ (god view)│  │  consumer-view.js    │  │   business-view.js   │ │
│  │  app.js   │  │  /api/consumer/{id}  │  │   /api/business/{id} │ │
│  └─────┬─────┘  └──────────────────────┘  └──────────────────────┘ │
│        │ WebSocket (ws://.../ws)                REST (HTTP)         │
└────────┼────────────────────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────────────────┐
│                       FastAPI Server (api/app.py)                   │
│                                                                     │
│  Routes:  GET /           GET /consumer/{id}   GET /business/{id}  │
│           POST /api/start  POST /api/stop                           │
│           GET /api/state   GET /api/transactions                    │
│           GET /api/db-status                                        │
│           WS  /ws                                                   │
│                                                                     │
│  WebSocketManager (ws_manager.py) — broadcast SimEvents to clients │
└────────┬────────────────────────────────────────────────────────────┘
         │ asyncio
┌────────▼────────────────────────────────────────────────────────────┐
│                    SimulationEngine (simulation/engine.py)          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  event_bus: asyncio.Queue  ──►  API event forwarder (task)  │   │
│  │  message_bus: dict[agent_id → asyncio.Queue]                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  consumers: dict[id → ConsumerAgent]    (5 agents)                 │
│  businesses: dict[id → BusinessAgent]   (8 B2C + 4 B2B = 12)      │
│  transactions: dict[txn_id → dict]                                 │
└────────┬──────────────────────────┬─────────────────────────────────┘
         │                          │
┌────────▼──────────┐   ┌───────────▼───────────────────────────────┐
│   ConsumerAgent   │   │           BusinessAgent                    │
│  (agents/         │   │          (agents/business.py)              │
│   consumer.py)    │   │                                            │
│                   │   │  business_type = "B2C" | "B2B"            │
│  State machine:   │   │                                            │
│  idle             │   │  B2C handles:                              │
│  → discovering    │   │    product_query → product_response        │
│  → considering    │◄──►    question      → question_answer         │
│  → converting     │   │    place_order   → order_confirmation      │
│  → post_purchase  │   │    review                                  │
│                   │   │    supply_confirmation (from B2B)          │
│  LLM calls:       │   │                                            │
│   shortlist       │   │  B2B handles:                              │
│   decision        │   │    supply_order (async delay, confirms)    │
│   review          │   │                                            │
└────────────────────   │  Auto-reorders from supplier when          │
                        │  inventory ≤ LOW_INVENTORY_THRESHOLD       │
                        └────────────────────────────────────────────┘
```

---

## Component Breakdown

### `agents/base.py` — BaseAgent

Abstract base for all agents. Provides:
- `send_message(to, type, content)` — writes to `message_bus[to]`, emits a `network_message` event for canvas visualization on key message types
- `receive_message(timeout)` — reads from own queue
- `emit_event(type, data, message)` — puts a `SimEvent` on the shared `event_bus`
- `call_llm(system, user)` — calls Claude Haiku (`claude-haiku-4-5-20251001`), expects JSON response

### `agents/consumer.py` — ConsumerAgent

Runs an asyncio task that cycles through a purchase funnel every few seconds. Impulse tendency (`0.0–1.0`) controls how often shopping is triggered from idle. Transaction tracking: each shopping session gets a UUID `transaction_id` propagated through all events and messages.

**Funnel stages:**

| Stage | Action | LLM? |
|---|---|---|
| idle | Random chance to start shopping | No |
| discovering | Broadcasts `product_query` to all B2C merchants | No |
| considering | Collects responses, calls LLM to shortlist top 3 | Yes |
| converting | Calls LLM to pick winner, places order | Yes |
| post_purchase | Sends review message to merchant | Yes (rating rationale) |

### `agents/business.py` — BusinessAgent

Unified B2C/B2B agent. Quality score (0–100) computed at init from catalog completeness, FAQs, policies, and company metadata. Score is included in consumer LLM prompts — imperfect catalogs (missing prices, sparse descriptions) cause real lost sales.

**Quality score deductions:**
- No/short description: −10
- No FAQs: −8; only 1 FAQ: −4
- No return policy: −6; no shipping policy: −4
- Missing founded year / employee count / headquarters: −3/−2/−2
- Per product: no price −8, no description −4, no name −5

### `simulation/engine.py` — SimulationEngine

Orchestrates the simulation lifecycle. On `start(mode="fresh")` or `start(mode="load")`, builds all agents from seed data (or restores from SQLite), activates them, creates asyncio tasks. On `stop()`, cancels all tasks, saves full state JSON to SQLite.

### `simulation/seed_data.py` — Seed Data

Pre-defined agents for reproducibility:

| Type | Count | Notes |
|---|---|---|
| B2B suppliers | 4 | ComponentsCorp, FabricWorld, MaterialsHub, FreshFarmSupply |
| B2C (high quality) | 5 | TechZone (~95), StyleHub (~90), FreshMart (~88), HomeNest (~92), GameVault (~89) |
| B2C (imperfect) | 3 | PixelDrop Tech (~45), VagueFashion (~52), QuickByte Foods (~61) |
| Consumers | 5 | Diverse demographics, budgets, behavioral traits |

### `simulation/events.py` — SimEvent

Dataclass carrying: `event_type`, `message`, `data`, `timestamp`, `from_agent_id`, `to_agent_id`, `transaction_id`. Events with `from_agent_id` + `to_agent_id` drive the network canvas visualization. Filter categories (`FILTER_CATEGORIES`) map UI filter names to sets of event types.

### `db/schema.py` + `db/persistence.py` — SQLite Persistence

Three tables:

| Table | Purpose |
|---|---|
| `simulation_state` | Full JSON snapshot of world state (kept last 3) |
| `transactions` | One row per consumer shopping session, updated as it progresses |
| `orders` | Individual fulfilled line items |

On startup, the UI queries `/api/db-status` → shows a modal letting the user choose "Load Previous" or "Start Fresh".

### `api/app.py` — FastAPI

- Serves static UI files and detail page HTML shells
- Relays `SimEvent` from `event_bus` to WebSocket clients via `WSManager.broadcast()`
- Intercepts `transaction_update` events to call `engine.record_transaction()` (persists to SQLite)
- REST endpoints return live agent state for the detail views

### `ui/` — Frontend

| File | Role |
|---|---|
| `index.html` + `app.js` + `style.css` | God view: 3-column layout — consumers, canvas+feed, businesses |
| `consumer.html` + `consumer-view.js` | Consumer detail: demographics, behavioral traits, funnel, sessions |
| `business.html` + `business-view.js` | Business detail: quality ring, catalog, orders, company info |

**Network canvas** (`app.js`): animated bezier curves between agent nodes. Consumers positioned left (x=30px), businesses right (x=W−30px). Edges have a 4-second TTL. B2B-to-B2B edges curve rightward. Message type determines edge color.

---

## Data Flow: Consumer Purchase

```
ConsumerAgent (idle)
  → decides to shop (impulse check)
  → _new_transaction()  ←── UUID assigned
  → state: discovering
  → send_message(each B2C, "product_query")  ──► network_message event → canvas edge
        │
        └─► BusinessAgent._handle_product_query()
              → search_catalog(query, category, max_price)
              → send_message(consumer, "product_response")

ConsumerAgent (considering)
  → collects all responses
  → call_llm(shortlist top 3 with quality scores)
  → state: converting
  → call_llm(pick winner)
  → send_message(merchant, "place_order")  ──► network_message event → canvas edge
        │
        └─► BusinessAgent._handle_order()
              → decrement inventory
              → total_revenue += amount
              → send_message(consumer, "order_confirmation")
              → if inventory ≤ threshold: _reorder_from_supplier()

ConsumerAgent (post_purchase)
  → call_llm(generate review text + rating)
  → send_message(merchant, "review")
  → _end_transaction(status="completed", ...)
  → emit transaction_update event  ──► API captures → save_transaction() → SQLite
  → state: idle
```

## Data Flow: B2B Restock

```
BusinessAgent (B2C, low inventory on SKU)
  → _reorder_from_supplier(sku)
  → send_message(supplier_id, "supply_order")  ──► canvas edge

BusinessAgent (B2B, receives supply_order)
  → asyncio.sleep(2–5s)  [simulates fulfillment delay]
  → total_revenue += quantity * 10
  → send_message(b2c_id, "supply_confirmation")  ──► canvas edge

BusinessAgent (B2C, receives supply_confirmation)
  → inventory[sku] += quantity
```

---

## Key Config (`config.py`)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | env | Claude API key |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | Cheap model for all agent LLM calls |
| `DB_PATH` | `simulation.db` | SQLite database file |
| `LOW_INVENTORY_THRESHOLD` | `5` | Triggers B2B restock |

---

## Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY=sk-...

# Start server (serves UI + API on port 8000)
python run.py

# Run tests
python -m pytest tests/ -v
```
