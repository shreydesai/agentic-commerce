import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
                await manager.broadcast({"type": "state", "data": sim.get_state()})
        except asyncio.TimeoutError:
            if manager.active_connections:
                await manager.broadcast({"type": "heartbeat"})
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


# ── WebSocket ───────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({"type": "state", "data": sim.get_state()})
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)
