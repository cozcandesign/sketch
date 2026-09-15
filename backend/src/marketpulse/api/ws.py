"""WebSocket hub ve `/ws` uç noktası (ARCHITECTURE.md §14).

Protokol: istemci `{"op": "subscribe"|"unsubscribe", "topics": [...]}` ve `{"op": "ping"}`
gönderir; sunucu `{"topic", "ts", "data"}` yayınları, `{"op": "pong"}` ve bağlantıda
`{"op": "hello"}` gönderir. Konu eşleşmesi: tam ad, `prefix.*` veya `*`.
"""

from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from marketpulse import __version__
from marketpulse.core.clock import Clock


def topic_matches(subscription: str, topic: str) -> bool:
    if subscription in {"*", topic}:
        return True
    if subscription.endswith(".*"):
        return topic.startswith(subscription[:-1])
    return False


class WsHub:
    """Bağlı istemciler ve abonelikleri. Yayın sırasında kopan istemci sessizce düşürülür."""

    def __init__(self) -> None:
        self._clients: dict[WebSocket, set[str]] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients[websocket] = set()

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.pop(websocket, None)

    def subscribe(self, websocket: WebSocket, topics: list[str]) -> set[str]:
        subs = self._clients.setdefault(websocket, set())
        subs.update(t for t in topics if isinstance(t, str) and t)
        return subs

    def unsubscribe(self, websocket: WebSocket, topics: list[str]) -> set[str]:
        subs = self._clients.setdefault(websocket, set())
        subs.difference_update(topics)
        return subs

    async def broadcast(self, topic: str, data: Any, ts: datetime) -> int:
        """Konuya abone istemcilere gönderir; ulaşılan istemci sayısını döner."""
        message = {"topic": topic, "ts": ts.isoformat(), "data": data}
        sent = 0
        for websocket, subs in list(self._clients.items()):
            if not any(topic_matches(s, topic) for s in subs):
                continue
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception as exc:  # kopan istemci: yayın diğerlerini etkilemez
                logger.debug("ws istemcisi düşürüldü: {err}", err=repr(exc))
                self.disconnect(websocket)
        return sent


async def ws_endpoint(websocket: WebSocket) -> None:
    hub: WsHub = websocket.app.state.hub
    clock: Clock = websocket.app.state.clock
    await hub.connect(websocket)
    await websocket.send_json(
        {"op": "hello", "api_version": __version__, "server_time": clock.now().isoformat()}
    )
    try:
        while True:
            message = await websocket.receive_json()
            await _handle(websocket, hub, clock, message)
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)


async def _handle(websocket: WebSocket, hub: WsHub, clock: Clock, message: Any) -> None:
    op = message.get("op") if isinstance(message, dict) else None
    topics = message.get("topics", []) if isinstance(message, dict) else []
    if op == "subscribe":
        subs = hub.subscribe(websocket, list(topics))
        await websocket.send_json({"op": "subscribed", "topics": sorted(subs)})
    elif op == "unsubscribe":
        subs = hub.unsubscribe(websocket, list(topics))
        await websocket.send_json({"op": "subscribed", "topics": sorted(subs)})
    elif op == "ping":
        await websocket.send_json({"op": "pong", "server_time": clock.now().isoformat()})
    else:
        await websocket.send_json({"op": "error", "message": f"bilinmeyen op: {op!r}"})
