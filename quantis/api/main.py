"""InvestEasy FastAPI Backend — Main Application Entry Point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from quantis.api.router import router as api_router
from quantis.api.live_router import router as live_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("investeasy.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("InvestEasy backend starting...")
    app.state.redis_sync = None
    app.state.queue = None
    yield
    logger.info("InvestEasy backend shutting down...")


app = FastAPI(
    title="InvestEasy API",
    description="Regime-Aware Quant Intelligence Platform for Indian Markets",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(live_router, prefix="/api/live")


# ── WebSocket — live price & regime ────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """Global live WebSocket — regime updates, price ticks, agent messages."""
    await manager.connect(websocket)
    logger.info("WebSocket client connected")
    try:
        while True:
            await asyncio.sleep(15)
            try:
                import yfinance as yf
                nifty = yf.Ticker("^NSEI")
                fi = nifty.fast_info
                nifty_price = float(fi.get("last_price", fi.get("previous_close", 22000)))
                vix_ticker = yf.Ticker("^INDIAVIX")
                vfi = vix_ticker.fast_info
                vix_val = float(vfi.get("last_price", vfi.get("previous_close", 14)))
            except Exception:
                import random
                nifty_price = round(22000 + random.uniform(-200, 200), 2)
                vix_val = round(14 + random.uniform(-2, 4), 2)

            await websocket.send_json({
                "type": "price_tick",
                "data": {
                    "nifty_level": round(nifty_price, 2),
                    "india_vix": round(vix_val, 2),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")


@app.get("/health")
async def health():
    return {"status": "ok", "name": "InvestEasy", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat()}
