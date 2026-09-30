import ssl
import json
import time
import base64
import threading
import contextlib
from collections import OrderedDict

import websocket

from gsuid_core.logger import logger

from .request_util import ios_base_header


def get_ws_continue_time() -> int:
    from ...dna_config.dna_config import DNAConfig

    return DNAConfig.get_config("WebSocketContinueTime").data or 300


def get_ws_wait_time() -> int:
    from ...dna_config.dna_config import DNAConfig

    return DNAConfig.get_config("WebSocketWaitTime").data or 5


def _close_quietly(ws: websocket.WebSocketApp) -> None:
    # 连接可能已被对端关闭，关闭失败不影响连接池回收
    with contextlib.suppress(websocket.WebSocketException, OSError):
        ws.close()


class WebSocketManager:
    """WebSocket 连接池管理器

    心跳：业务层心跳（每10秒发送 {"event": "ping", "data": {"userId": ...}}）
    """

    WS_URL = "wss://dnabbs-api.yingxiong.com:8180/ws-community-websocket"
    MAX_POOL_SIZE = 20
    HEARTBEAT_INTERVAL = 10

    def __init__(self):
        # _pool 存储 (ws, timestamp) 元组
        self._pool: OrderedDict[tuple[str, str], tuple[websocket.WebSocketApp, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._ready_events: dict[tuple[str, str], threading.Event] = {}

    def _extract_user_id(self, token: str) -> str:
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        # token 是外部输入：base64 / JSON / UTF-8 解码失败都是 ValueError 子类
        try:
            data = json.loads(base64.urlsafe_b64decode(payload))
        except ValueError:
            return ""
        return str(data["userId"]) if isinstance(data, dict) and "userId" in data else ""

    def _start_heartbeat(self, ws: websocket.WebSocketApp, user_id: str) -> None:
        def heartbeat_loop():
            while True:
                time.sleep(self.HEARTBEAT_INTERVAL)
                try:
                    if ws.sock and ws.sock.connected:
                        ws.send(json.dumps({"event": "ping", "data": {"userId": user_id}}))
                    else:
                        break
                except Exception:
                    break

        threading.Thread(target=heartbeat_loop, daemon=True).start()

    def _create_connection(
        self, token: str, dev_code: str, ready_event: threading.Event
    ) -> websocket.WebSocketApp | None:
        try:
            key = (token, dev_code)
            user_id = self._extract_user_id(token)

            def _remove_from_pool():
                with self._lock:
                    self._pool.pop(key, None)
                    self._ready_events.pop(key, None)

            def on_message(ws, message):
                # 快速过期检查
                logger.debug(f"[DNA WebSocket] received message: {message}")
                with self._lock:
                    if (item := self._pool.get(key)) and time.time() - item[1] > get_ws_continue_time():
                        _close_quietly(ws)

            def on_error(ws, error):
                logger.debug(f"[DNA WebSocket] on_error is called (error: {error})")
                _remove_from_pool()
                ready_event.set()  # 即使出错也要释放等待

            def on_close(ws, close_status_code, close_msg):
                logger.debug(f"[DNA WebSocket] on_close is called (code: {close_status_code}, message: {close_msg})")
                _remove_from_pool()

            def on_open(ws):
                logger.debug("[DNA WebSocket] on_open is successed")
                with self._lock:
                    self._pool[key] = (ws, time.time())
                self._start_heartbeat(ws, user_id)
                ready_event.set()  # 连接成功，释放等待

            ws = websocket.WebSocketApp(
                self.WS_URL,
                header=[
                    f"{k}:{v}"
                    for k, v in {
                        "sourse": "ios",
                        "appVersion": ios_base_header.get("version", "1.2.0"),
                        "token": token,
                        "devCode": dev_code,
                    }.items()
                ],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            threading.Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True).start()
            return ws
        except Exception as e:
            logger.warning(f"[DNA WebSocket] connection failed (error: {e})")
            ready_event.set()
            return None

    def _is_expired(self, key: tuple[str, str]) -> bool:
        if not (item := self._pool.get(key)):
            return True
        return time.time() - item[1] > get_ws_continue_time()

    def _cleanup_connection(self, key: tuple[str, str]):
        if item := self._pool.pop(key, None):
            _close_quietly(item[0])

    def get_connection(
        self, token: str, dev_code: str, wait_ready: bool = False, timeout: float = 5
    ) -> websocket.WebSocketApp | None:
        if not token or not dev_code:
            return None
        key = (token, dev_code)

        with self._lock:
            # 检查连接是否存在且有效（未过期）
            if (item := self._pool.get(key)) and time.time() - item[1] <= get_ws_continue_time():
                # 续时：更新时间戳以延长连接过期时间
                self._pool[key] = (item[0], time.time())
                self._pool.move_to_end(key)
                return item[0]

            # 清理当前请求的无效连接
            if key in self._pool:
                self._cleanup_connection(key)

            # 批量清理其他过期连接
            for expired_key in [k for k in self._pool if self._is_expired(k)]:
                self._cleanup_connection(expired_key)

            # LRU 淘汰：超过上限则移除最老的
            while len(self._pool) >= self.MAX_POOL_SIZE:
                self._cleanup_connection(self._pool.popitem(last=False)[0])

            # 创建新连接
            ready_event = threading.Event()
            self._ready_events[key] = ready_event

            ws = self._create_connection(token, dev_code, ready_event)
            if not ws:
                self._ready_events.pop(key, None)
                return None

            self._pool[key] = (ws, time.time())  # on_open 会更新为实际建立时间

        # 等待连接建立
        if wait_ready:
            logger.debug(f"[DNA WebSocket] waiting for connection to be established (timeout {timeout}s)...")
            if ready_event.wait(timeout):
                with self._lock:
                    if key in self._pool:
                        logger.debug("[DNA WebSocket] connection is ready")
                        return self._pool[key][0]
                    else:
                        logger.warning("[DNA WebSocket] connection is failed")
                        return None
            else:
                logger.warning(f"[DNA WebSocket] waiting for connection to be established timeout ({timeout}s)")
                # 超时后清理连接
                with self._lock:
                    self._cleanup_connection(key)
                    self._ready_events.pop(key, None)
                return None

        return ws


# 全局单例
_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    global _ws_manager
    return _ws_manager or (_ws_manager := WebSocketManager())
