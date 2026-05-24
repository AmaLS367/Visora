import logging
from typing import Any, cast

import httpx

from backend.config import Settings, get_settings

logger = logging.getLogger("backend.bridge")


class UnityBridge:
    """
    HTTP Client bridge for AnkleBreaker Unity Editor plugin.
    Implements a automatic port fallback mechanism (default port 7890, fallback 7891).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.unity_bridge_url
        self.default_port = self.settings.unity_bridge_port
        self.fallback_port = self.settings.unity_bridge_fallback_port
        self._active_port: int | None = None
        self.client = httpx.AsyncClient(timeout=self.settings.unity_bridge_timeout_seconds)

    async def get_active_port(self) -> int:
        """
        Dynamically detects and returns the active Unity bridge port.
        Tries the default port first, falling back to the fallback port if the default fails.
        """
        if self._active_port is not None:
            return self._active_port

        for port in [self.default_port, self.fallback_port]:
            test_url = f"{self.base_url}:{port}/api/ping"
            try:
                logger.debug(f"Trying to ping AnkleBreaker on {test_url}...")
                response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
                if response.status_code == 200:
                    logger.info(f"Successfully connected to AnkleBreaker on port {port}")
                    self._active_port = port
                    return port
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
                logger.warning(f"AnkleBreaker not responding on port {port}")
                continue

        msg = f"AnkleBreaker is not reachable on ports {self.default_port} or {self.fallback_port}."
        logger.error(msg)
        raise ConnectionError(msg)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Helper to send HTTP requests to AnkleBreaker using the active port."""
        port = await self.get_active_port()
        url = f"{self.base_url}:{port}/{path.lstrip('/')}"

        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            # If our active port was cached but failed, invalidate it and retry once
            logger.warning(f"Connection failed on port {port}. Resetting active port and retrying... Error: {e}")
            self._active_port = None

            # Retry with newly detected port
            port = await self.get_active_port()
            url = f"{self.base_url}:{port}/{path.lstrip('/')}"
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    async def ping(self) -> bool:
        """Pings the Unity editor HTTP bridge."""
        try:
            response = await self._request("GET", "/api/ping")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def execute_code(self, code: str) -> dict[str, Any]:
        """
        Sends C# or Editor script code to Unity to be dynamically compiled and executed.
        Returns a dictionary containing execution status, results, and logs.
        """
        response = await self._request("POST", "/api/editor/execute-code", json={"code": code})
        return cast(dict[str, Any], response.json())

    async def get_editor_state(self) -> dict[str, Any]:
        """Returns current Unity editor state including play mode, compilation, and active scene."""
        response = await self._request("GET", "/api/editor/state")
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

    async def close(self) -> None:
        """Closes the underlying HTTPX client."""
        await self.client.aclose()
