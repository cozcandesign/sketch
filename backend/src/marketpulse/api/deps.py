"""Router bağımlılıkları: `app.state` üzerinden paylaşılan nesneler."""

from fastapi import Request

from marketpulse.api.live_relay import LiveState
from marketpulse.api.outbox_relay import RelayState
from marketpulse.api.ws import WsHub
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.storage.repository import Repository


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_repo(request: Request) -> Repository:
    repo: Repository = request.app.state.repo
    return repo


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_hub(request: Request) -> WsHub:
    hub: WsHub = request.app.state.hub
    return hub


def get_relay_state(request: Request) -> RelayState:
    state: RelayState = request.app.state.relay_state
    return state


def get_live_state(request: Request) -> LiveState:
    state: LiveState = request.app.state.live_state
    return state
