# backend/routers/api_client_router.py

"""API Client Router - WebSocket endpoint for client connections.

Clients actively connect to the server via WebSocket. The server sends
file operation commands through the WebSocket, and clients execute them
and return results. This works even when clients are behind NAT/firewalls
since only the client initiates the connection.
"""

import asyncio
import concurrent.futures
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.crud import backend_crud
from backend.schemas.enums import BackendType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-client", tags=["API Client"])


# ==========================================
# Connection Registry (in-memory)
# ==========================================
# backend_id -> WebSocket
_connections: Dict[str, WebSocket] = {}

# request_id -> concurrent.futures.Future (thread-safe, for request-response pattern)
_pending_requests: Dict[str, concurrent.futures.Future] = {}

# backend_id -> ClientInfo
_client_info: Dict[str, Dict[str, Any]] = {}


def get_client_connection(backend_id: str) -> Optional[WebSocket]:
    """Get an active WebSocket connection by backend ID."""
    ws = _connections.get(backend_id)
    if ws is None:
        return None
    return ws


def get_client_info(backend_id: str) -> Dict[str, Any]:
    """Return the client info dict reported by the connected API client.

    Contains keys like ``platform`` / ``root_dir`` / ``hostname`` / ``pid``
    (from the client's ``register_info`` message).  Returns ``{}`` when
    the client is not connected or has not reported info yet.
    """
    return _client_info.get(backend_id, {})


async def _send_abort(ws: WebSocket, request_id: str, method: str) -> None:
    """Fire-and-forget: 通知客户端中止 *request_id* 对应的执行进程。

    超时 / 取消时调用——调用方已放弃等待响应,因此不期待客户端回复。
    """
    try:
        await ws.send_json({
            "type": "command",
            "request_id": request_id,
            "method": "abort",
            "params": {"request_id": request_id},
        })
        logger.info("[ROUTER] send_command: sent abort for %s method=%s", request_id, method)
    except Exception:
        logger.warning("[ROUTER] send_command: failed to send abort for %s", request_id, exc_info=True)


async def send_command(backend_id: str, method: str, params: dict, timeout: float = 60.0) -> dict:
    """Send a command through WebSocket and wait for the client's response.

    Args:
        backend_id: The backend ID to route the command to.
        method: The method name to execute on the client.
        params: The parameters for the method.
        timeout: Maximum seconds to wait for a response.

    Returns:
        The result dict from the client.

    Raises:
        ConnectionError: If the client is not connected.
        TimeoutError: If the client does not respond in time.
        RuntimeError: If the client returns an error.
    """
    ws = _connections.get(backend_id)
    if ws is None:
        raise ConnectionError(f"API client for backend '{backend_id}' is not connected")

    request_id = str(uuid.uuid4())
    cfuture: concurrent.futures.Future = concurrent.futures.Future()
    _pending_requests[request_id] = cfuture

    logger.info("[ROUTER] send_command: request_id=%s method=%s params=%s", request_id, method, params)
    try:
        await ws.send_json({
            "type": "command",
            "request_id": request_id,
            "method": method,
            "params": params,
        })
        logger.info("[ROUTER] send_command: sent, waiting for response...")

        result = await asyncio.wait_for(
            asyncio.wrap_future(cfuture), timeout=timeout
        )
        logger.info("[ROUTER] send_command: got response for %s", request_id)
        return result
    except asyncio.TimeoutError:
        logger.error("[ROUTER] send_command: TIMEOUT for %s method=%s after %ss", request_id, method, timeout)
        await _send_abort(ws, request_id, method)
        raise TimeoutError(f"API client for backend '{backend_id}' timed out on method '{method}'")
    except asyncio.CancelledError:
        # 上游被取消(用户中止生成 / 工具层超时):客户端进程仍在运行,
        # 补发 abort 通知客户端杀掉进程树,避免残留孤儿进程。
        logger.info("[ROUTER] send_command: CANCELLED for %s method=%s, sending abort", request_id, method)
        await _send_abort(ws, request_id, method)
        raise
    except WebSocketDisconnect:
        _connections.pop(backend_id, None)
        _client_info.pop(backend_id, None)
        raise ConnectionError(f"API client for backend '{backend_id}' disconnected")
    finally:
        _pending_requests.pop(request_id, None)


async def _verify_backend_api_key(backend_id: str, api_key: str) -> bool:
    """Verify backend exists and api_key matches. Returns True if valid."""
    try:
        async for db in get_db():
            db_obj = await backend_crud.get_backend(db, backend_id)
            if not db_obj:
                return False
            if db_obj.backendType != BackendType.API.value:
                return False
            stored_key = db_obj.configData.get("api_key")
            if not stored_key or stored_key != api_key:
                return False
            return True
    except Exception as e:
        logger.error("Error verifying API client: %s", e)
        return False


async def _handle_client_message(backend_id: str, ws: WebSocket, data: dict):
    """Handle incoming messages from the client."""
    msg_type = data.get("type")
    logger.info("[ROUTER] handle_client_message: backend=%s type=%s", backend_id, msg_type)

    if msg_type == "response":
        request_id = data.get("request_id")
        logger.info("[ROUTER] handle_client_message: response for request_id=%s", request_id)
        future = _pending_requests.get(request_id)
        if future and not future.done():
            future.set_result(data.get("result", {}))
        else:
            logger.warning("[ROUTER] handle_client_message: no pending future for request_id=%s (done=%s exists=%s)",
                           request_id, future.done() if future else False, future is not None)

    elif msg_type == "error":
        request_id = data.get("request_id")
        future = _pending_requests.get(request_id)
        if future and not future.done():
            future.set_exception(RuntimeError(data.get("message", "Client error")))
        else:
            logger.warning("Received error for unknown request: %s", request_id)

    elif msg_type == "register_info":
        _client_info[backend_id] = data.get("info", {})
        logger.info("API client info updated for backend %s: %s", backend_id, data.get("info"))

    else:
        logger.warning("Unknown message type from client %s: %s", backend_id, msg_type)


@router.websocket("/ws/{backend_id}")
async def websocket_endpoint(ws: WebSocket, backend_id: str):
    """WebSocket endpoint for API client connections.

    Clients connect to: ws://server/api/api-client/ws/{backend_id}

    After connection, clients must send an auth message first:
    {"type": "auth", "api_key": "xxx"}

    Then optionally send a register_info message:
    {"type": "register_info", "info": {"root_dir": "/path", "hostname": "my-pc"}}
    """
    await ws.accept()

    # Wait for auth message
    try:
        auth_msg = await asyncio.wait_for(ws.receive_json(), timeout=10)
    except asyncio.TimeoutError:
        await ws.close(code=4003, reason="Authentication timeout")
        return

    if auth_msg.get("type") != "auth" or not auth_msg.get("api_key"):
        await ws.close(code=4003, reason="Invalid auth message")
        return

    api_key = auth_msg["api_key"]
    valid = await _verify_backend_api_key(backend_id, api_key)
    if not valid:
        await ws.close(code=4003, reason="Invalid backend ID or API key")
        return

    # Auth success
    try:
        await ws.send_json({"type": "auth_ok"})
    except Exception:
        return

    # Check if another connection exists for this backend
    existing_ws = _connections.get(backend_id)
    if existing_ws:
        try:
            await existing_ws.close(code=4001, reason="Replaced by new connection")
        except Exception:
            pass
    _connections[backend_id] = ws
    connected_at = time.time()

    logger.info("API client connected: backend=%s", backend_id)

    # Try to send a welcome message (client may not be ready yet, that's ok)
    try:
        await ws.send_json({
            "type": "welcome",
            "backend_id": backend_id,
            "message": "Connected to MamboChat API backend",
        })
    except Exception:
        pass

    try:
        while True:
            data = await ws.receive_json()
            await _handle_client_message(backend_id, ws, data)
    except WebSocketDisconnect:
        logger.info("API client disconnected: backend=%s", backend_id)
    except Exception as e:
        logger.error("API client error (backend=%s): %s", backend_id, e)
    finally:
        # Clean up
        old_ws = _connections.pop(backend_id, None)
        if old_ws is not ws:
            # A new connection replaced this one, don't clean up
            pass
        _client_info.pop(backend_id, None)

        # Fail any pending requests
        for req_id, future in list(_pending_requests.items()):
            if not future.done():
                future.set_exception(ConnectionError(f"API client for backend '{backend_id}' disconnected"))


@router.get("/status/{backend_id}", summary="Get client connection status")
async def get_client_status(backend_id: str):
    """Check if a client is currently connected for a given backend."""
    ws = _connections.get(backend_id)
    if ws is not None:
        info = _client_info.get(backend_id, {})
        return {
            "connected": True,
            "client_info": info,
        }
    return {"connected": False}
