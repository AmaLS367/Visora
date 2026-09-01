import asyncio
import logging
import time
from typing import Any, cast

import httpx

from backend.bridge.exceptions import (
    BridgeConnectionError,
    BridgeHTTPError,
    BridgeTimeoutError,
)
from backend.config import Settings, get_settings

logger = logging.getLogger("backend.bridge")


class UnityBridge:
    """
    HTTP Client bridge for AnkleBreaker Unity Editor plugin.
    Implements dynamic multi-port discovery, fallback, retry mechanics, and typed exceptions.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.unity_bridge_url
        self.default_port = self.settings.unity_bridge_port
        self.fallback_port = self.settings.unity_bridge_fallback_port
        self._active_port: int | None = None
        self.client = httpx.AsyncClient(timeout=self.settings.unity_bridge_timeout_seconds)

    @property
    def candidate_ports(self) -> list[int]:
        """Ordered list of candidate ports to scan or connect to."""
        ports: list[int] = []
        # Priority 1: Default port
        if self.default_port not in ports:
            ports.append(self.default_port)
        # Priority 2: Fallback port
        if self.fallback_port not in ports:
            ports.append(self.fallback_port)
        # Priority 3: Configured scan ports list
        for p in self.settings.unity_bridge_ports_to_scan:
            if p not in ports:
                ports.append(p)
        return ports

    async def get_active_port(self, force_refresh: bool = False) -> int:
        """
        Dynamically detects and returns the active Unity bridge port.
        Tries candidate ports in priority order, caching the active one.
        """
        if self._active_port is not None and not force_refresh:
            return self._active_port

        ports = self.candidate_ports
        for port in ports:
            test_url = f"{self.base_url}:{port}/api/ping"
            try:
                logger.debug(f"Pinging AnkleBreaker on {test_url}...")
                response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
                if response.status_code == 200:
                    logger.info(f"Successfully connected to AnkleBreaker on port {port}")
                    self._active_port = port
                    return port
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
                logger.debug(f"AnkleBreaker not responding on port {port}")
                continue

        msg = f"AnkleBreaker is not reachable on any configured port ({', '.join(str(p) for p in ports)})."
        logger.error(msg)
        raise BridgeConnectionError(message=msg, ports=ports)

    async def scan_available_ports(self) -> list[dict[str, Any]]:
        """
        Scans all candidate ports, reporting availability and round-trip latency.
        """
        results: list[dict[str, Any]] = []
        for port in self.candidate_ports:
            test_url = f"{self.base_url}:{port}/api/ping"
            start = time.perf_counter()
            try:
                response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
                latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
                is_open = response.status_code == 200
                results.append({"port": port, "is_open": is_open, "latency_ms": latency_ms if is_open else None})
            except Exception:
                results.append({"port": port, "is_open": False, "latency_ms": None})
        return results

    async def ping(self, port: int | None = None) -> tuple[bool, float | None]:
        """
        Pings the Unity editor HTTP bridge and measures roundtrip latency.
        Returns a tuple of (is_reachable, latency_ms).
        """
        target_port = port or self._active_port
        if target_port is None:
            try:
                target_port = await self.get_active_port()
            except BridgeConnectionError:
                return False, None

        test_url = f"{self.base_url}:{target_port}/api/ping"
        start = time.perf_counter()
        try:
            response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
            latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
            return response.status_code == 200, latency_ms if response.status_code == 200 else None
        except Exception as e:
            logger.debug(f"Ping failed on port {target_port}: {e}")
            return False, None

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """
        Sends HTTP requests to AnkleBreaker using the active port with automatic retry and error mapping.
        """
        max_attempts = max(1, self.settings.unity_bridge_max_retries + 1)
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                port = await self.get_active_port(force_refresh=(attempt > 0 and self._active_port is None))
                url = f"{self.base_url}:{port}/{path.lstrip('/')}"
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                logger.warning(f"Bridge connection error on attempt {attempt + 1}/{max_attempts}: {e}")
                self._active_port = None
                last_exception = e
            except httpx.ReadTimeout as e:
                logger.warning(f"Bridge read timeout on attempt {attempt + 1}/{max_attempts}: {e}")
                last_exception = e
            except httpx.HTTPStatusError as e:
                logger.error(f"Bridge HTTP status error {e.response.status_code} for {path}: {e}")
                raise BridgeHTTPError(
                    message=f"Bridge HTTP error {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                ) from e
            except BridgeConnectionError as e:
                last_exception = e
                break

            if attempt < max_attempts - 1:
                await asyncio.sleep(self.settings.unity_bridge_retry_backoff * (attempt + 1))

        if isinstance(last_exception, (httpx.ReadTimeout, httpx.ConnectTimeout)):
            raise BridgeTimeoutError(
                message=f"Bridge request to '{path}' timed out after {self.settings.unity_bridge_timeout_seconds}s.",
                timeout_seconds=self.settings.unity_bridge_timeout_seconds,
            ) from last_exception

        msg = f"Bridge request to '{path}' failed after {max_attempts} attempts."
        logger.error(msg)
        raise BridgeConnectionError(message=msg, ports=self.candidate_ports) from last_exception

    async def execute_code(self, code: str) -> dict[str, Any]:
        """
        Sends C# or Editor script code to Unity to be dynamically compiled and executed.
        Returns a dictionary containing execution status, results, and logs.
        """
        response = await self._request("POST", "/api/editor/execute-code", json={"code": code})
        return cast(dict[str, Any], response.json())

    async def get_editor_state(self) -> dict[str, Any]:
        """Returns current Unity editor state including play mode, compilation, and active scene."""
        response = await self._request("POST", "/api/editor/state")
        return cast(dict[str, Any], response.json())

    async def set_play_mode(self, active: bool) -> dict[str, Any]:
        """
        Sets the Unity Editor Play Mode state (active=True to play, active=False to stop).
        """
        response = await self._request("POST", "/api/editor/play-mode", json={"action": "play" if active else "stop"})
        return cast(dict[str, Any], response.json())

    async def save_scene(self) -> dict[str, Any]:
        """
        Forces the Unity Editor to save the currently active scene.
        """
        response = await self._request("POST", "/api/scene/save")
        return cast(dict[str, Any], response.json())

    async def get_compilation_errors(self) -> dict[str, Any]:
        """
        Retrieves active compiler errors and warnings from the Unity project.
        """
        response = await self._request("GET", "/api/compilation/errors")
        return cast(dict[str, Any], response.json())

    async def get_queue_status(self, ticket_id: str) -> dict[str, Any]:
        """
        Checks the status of a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("GET", "/api/queue/status", params={"ticketId": ticket_id})
        return cast(dict[str, Any], response.json())

    async def cancel_queue_ticket(self, ticket_id: str) -> dict[str, Any]:
        """
        Attempts to cancel a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("POST", "/api/queue/cancel", json={"ticketId": ticket_id})
        return cast(dict[str, Any], response.json())

    async def close(self) -> None:
        """Closes the underlying HTTPX client."""
        await self.client.aclose()

    async def __aenter__(self) -> "UnityBridge":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
