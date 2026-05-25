import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.ws_manager import ConnectionManager
from simulation.engine import SimulationEngine
from db.schema import has_saved_state, get_saved_meta
from config import DB_PATH

manager = ConnectionManager()
sim = SimulationEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    sim.initialize()
    asyncio.create_task(_event_forwarder())
    yield


app = FastAPI(title="Agentic Commerce Simulator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="ui"), name="static")


async def _event_forwarder():
    event_counter = 0
    while True:
        try:
            event = await asyncio.wait_for(sim.event_bus.get(), timeout=0.5)
            event_dict = event.model_dump(mode="json")

            # ACP messages go to a separate log and WS channel so they don't
            # pollute the activity feed event history.
            if event.event_type == "acp_message":
                sim.message_log.append(event_dict)
                if len(sim.message_log) > 300:
                    sim.message_log = sim.message_log[-300:]
                await manager.broadcast({"type": "msg", "data": event_dict})
                continue

            sim.event_history.append(event_dict)
            if len(sim.event_history) > 600:
                sim.event_history = sim.event_history[-600:]

            # Track transactions from transaction_update events
            if event.event_type == "transaction_update":
                txn = event.data.get("transaction")
                if txn:
                    sim.record_transaction(txn)

            event_counter += 1
            await manager.broadcast({"type": "event", "data": event_dict})
            if event_counter % 4 == 0:
                state = sim.get_state()
                state["speed_factor"] = sim.speed_factor
                state["active_scenarios"] = sim.active_scenarios
                await manager.broadcast({"type": "state", "data": state})
        except asyncio.TimeoutError:
            if manager.active_connections:
                await manager.broadcast({"type": "heartbeat", "speed_factor": sim.speed_factor})
        except Exception as e:
            print(f"Event forwarder error: {e}")


# ── Pages ───────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("ui/index.html")


@app.get("/consumer/{agent_id}")
async def consumer_page(agent_id: str):
    return FileResponse("ui/consumer.html")


@app.get("/business/{agent_id}")
async def business_page(agent_id: str):
    return FileResponse("ui/business.html")


# ── API ─────────────────────────────────────────────────────────
@app.get("/api/state")
async def get_state():
    return sim.get_state()


@app.get("/api/db-status")
async def db_status():
    has_data = has_saved_state(DB_PATH)
    meta = get_saved_meta(DB_PATH) if has_data else None
    return {"has_saved_state": has_data, "meta": meta}


@app.post("/api/start")
async def start_simulation(mode: str = "fresh"):
    await sim.start(mode=mode)
    return {"status": "started", "state": sim.get_state()}


@app.post("/api/stop")
async def stop_simulation():
    await sim.stop()
    return {"status": "stopped", "state": sim.get_state()}


@app.get("/api/consumer/{agent_id}")
async def get_consumer(agent_id: str):
    c = sim.consumers.get(agent_id)
    if not c:
        return {"error": "not found"}
    txns = [t for t in sim.transactions.values() if t.get("consumer_id") == agent_id]
    return {**c.get_state_dict(), "transactions": txns, "purchase_history": c.purchase_history}


@app.get("/api/business/{agent_id}")
async def get_business(agent_id: str):
    b = sim.businesses.get(agent_id)
    if not b:
        return {"error": "not found"}
    return {**b.get_state_dict(), "orders": b.orders[-20:], "ratings": b.ratings}


@app.get("/api/transactions")
async def get_transactions():
    return {"transactions": list(sim.transactions.values())}


@app.get("/api/messages")
async def get_messages(limit: int = 100):
    return {"messages": sim.message_log[-limit:]}


@app.post("/api/scenario")
async def apply_scenario(payload: dict = Body(...)):
    """Apply a market scenario to the live simulation."""
    scenario_type = payload.get("type", "")
    if not sim.running:
        return {"message": "Simulation is not running — start it first"}
    message = sim.apply_scenario(scenario_type)
    from simulation.events import SimEvent
    event = SimEvent(
        event_type="scenario_applied",
        agent_id="system",
        agent_name="Market System",
        agent_type="system",
        data={"scenario": scenario_type, "message": message},
        message=f"⚡ Scenario '{scenario_type}': {message}",
    )
    await sim.event_bus.put(event)
    return {"message": message, "active_scenarios": sim.active_scenarios}


@app.get("/api/scenarios/active")
async def get_active_scenarios():
    return {"active_scenarios": sim.active_scenarios}


@app.post("/api/speed")
async def set_speed(factor: float = 1.0):
    """Set simulation speed multiplier (0.25–5.0)."""
    sim.set_speed(factor)
    return {"speed_factor": sim.speed_factor}


# ── WebSocket ───────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({"type": "state", "data": sim.get_state()})
    # Hydrate the feed with recent events so the activity log survives page navigation
    if sim.event_history:
        await websocket.send_json({"type": "history", "data": sim.event_history[-100:]})
    # Hydrate the ACP message log
    if sim.message_log:
        await websocket.send_json({"type": "msg_history", "data": sim.message_log[-100:]})
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)
