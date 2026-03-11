import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from uk_management_bot.api.auth.service import verify_access_token
from uk_management_bot.services.redis_pubsub import subscribe_to_requests, subscribe_to_shifts

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    async def connect(self, ws: WebSocket):
        await ws.accept()

    def disconnect(self, ws: WebSocket):
        pass  # cleanup is handled in the finally block via pubsub.unsubscribe()


manager = ConnectionManager()
shifts_manager = ConnectionManager()


@router.websocket("/kanban")
async def kanban_ws(websocket: WebSocket, token: str = Query(...)):
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    pubsub = None
    try:
        pubsub = await subscribe_to_requests()
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        manager.disconnect(websocket)
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from pubsub", exc_info=True)


@router.websocket("/shifts")
async def shifts_ws(websocket: WebSocket, token: str = Query(...)):
    payload = verify_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await shifts_manager.connect(websocket)
    pubsub = None
    try:
        pubsub = await subscribe_to_shifts()
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Shifts WebSocket error")
    finally:
        shifts_manager.disconnect(websocket)
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
            except Exception:
                logger.warning("Failed to unsubscribe from shifts pubsub", exc_info=True)
