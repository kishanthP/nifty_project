import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import AuthError, get_or_create_user, verify_token
from app.models import Instrument
from app.services.price_cache import PriceCache
from app.services.realtime import RealtimeHub

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/market")
async def market_socket(websocket: WebSocket) -> None:
    """Live prices for everyone; alert events after {"type": "auth", "token": "..."}.

    The token travels in a message instead of the URL so it never lands in server logs.
    """
    await websocket.accept()
    app = websocket.app
    hub: RealtimeHub = app.state.hub
    cache: PriceCache = app.state.cache
    client = hub.register(websocket)
    try:
        async with app.state.session_factory() as db:
            symbols = list(await db.scalars(select(Instrument.symbol).where(Instrument.is_active)))
        for quote in await cache.get_quotes(symbols):
            await client.send(f'{{"type":"quote","data":{quote.model_dump_json()}}}')

        while True:
            message = await websocket.receive_json()
            kind = message.get("type") if isinstance(message, dict) else None
            if kind == "ping":
                await client.send(json.dumps({"type": "pong"}))
            elif kind == "auth":
                try:
                    identity = await verify_token(str(message.get("token", "")))
                    async with app.state.session_factory() as db:
                        user = await get_or_create_user(db, identity)
                    client.user_id = user.id
                    await client.send(json.dumps({"type": "auth_ok"}))
                except AuthError as exc:
                    await client.send(json.dumps({"type": "auth_error", "detail": exc.message}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        hub.unregister(client)
