import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.ws_manager import ConnectionManager
from simulation.engine import SimulationEngine


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
            if len(sim.event_history) > 500:
                sim.event_history = sim.event_history[-500:]
            event_counter += 1
            await manager.broadcast({"type": "event", "data": event_dict})
            if event_counter % 3 == 0:
                await manager.broadcast({"type": "state", "data": sim.get_state()})
        except asyncio.TimeoutError:
            if manager.active_connections:
                await manager.broadcast({"type": "heartbeat", "data": {}})
        except Exception as e:
            print(f"Event forwarder error: {e}")


@app.get("/")
async def root():
    return FileResponse("ui/index.html")


@app.get("/api/state")
async def get_state():
    return sim.get_state()


@app.post("/api/start")
async def start_simulation():
    await sim.start()
    return {"status": "started", "state": sim.get_state()}


@app.post("/api/stop")
async def stop_simulation():
    await sim.stop()
    return {"status": "stopped", "state": sim.get_state()}


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
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
