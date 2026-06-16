import uuid

from fastapi import WebSocket


class ConnectionManager:
    """Registre en mémoire des connexions WebSocket actives par utilisateur."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, list[WebSocket]] = {}

    def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._connections.get(user_id, [])):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(user_id, websocket)


manager = ConnectionManager()
