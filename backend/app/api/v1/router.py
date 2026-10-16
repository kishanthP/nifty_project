from fastapi import APIRouter

from app.api.v1 import alerts, devices, health, market, users, ws

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(ws.router, tags=["realtime"])
