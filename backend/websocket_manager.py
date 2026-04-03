"""
WebSocket connection manager — broadcasts events to all connected dashboard clients.
"""
import json
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        """Send a JSON message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_event(self, event: dict):
        """Broadcast a live agent event to the dashboard."""
        await self.broadcast({"type": "event", "data": event})

    async def send_stats_update(self, stats: dict):
        """Broadcast updated stats."""
        await self.broadcast({"type": "stats_update", "data": stats})
