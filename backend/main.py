"""
AI GitOps Agent — FastAPI Backend
Main entry point: webhook listener, WebSocket live feed, REST API
"""
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from websocket_manager import WebSocketManager
from webhook import handle_github_webhook
from demo_runner import DemoRunner

load_dotenv()

app = FastAPI(title="AI GitOps Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ws_manager = WebSocketManager()
demo_runner = DemoRunner(ws_manager)

# ─── Stats in memory ─────────────────────────────────────────────────────────
stats = {
    "issues_detected": 0, 
    "prs_created": 0, 
    "files_analyzed": 0, 
    "fixes_generated": 0, 
    "repos_watched": 1
}
events_log: list[dict] = []


def push_event(event: dict):
    events_log.insert(0, event)
    if len(events_log) > 50:
        events_log.pop()
    
    # Corrected Stat Tracking
    etype = event.get("type")
    if etype == "analyzing":
        stats["files_analyzed"] += len(event.get("files", []))
    elif etype == "issue_detected":
        stats["issues_detected"] += 1
    elif etype == "fix_generated":
        stats["fixes_generated"] += 1
    elif etype == "pr_created":
        stats["prs_created"] += 1


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "AI GitOps Agent running 🚀", "demo_mode": os.getenv("DEMO_MODE", "true") == "true"}


@app.get("/api/stats")
async def get_stats():
    return stats


@app.get("/api/events")
async def get_events():
    return events_log


@app.post("/api/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive GitHub webhook events and process asynchronously."""
    try:
        payload = await request.json()
        event_type = request.headers.get("X-GitHub-Event", "unknown")
        background_tasks.add_task(
            handle_github_webhook, payload, event_type, ws_manager, push_event
        )
        return JSONResponse({"status": "received"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/demo/trigger")
async def trigger_demo(background_tasks: BackgroundTasks):
    """Manually trigger a demo event sequence."""
    background_tasks.add_task(demo_runner.run_scenario, push_event)
    return {"status": "Demo scenario started"}


@app.post("/api/demo/start")
async def start_demo_loop(background_tasks: BackgroundTasks):
    """Start continuous demo event loop."""
    background_tasks.add_task(demo_runner.run_loop, push_event)
    return {"status": "Demo loop started"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    # Send current events on connect
    await websocket.send_json({"type": "init", "stats": stats, "events": events_log[:10]})
    try:
        while True:
            # Keepalive ping
            await asyncio.sleep(30)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
