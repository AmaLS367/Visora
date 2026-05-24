import os
import httpx
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("visora.bridge")

class UnityBridge:
    """
    HTTP Client bridge for AnkleBreaker Unity Editor plugin.
    Implements a automatic port fallback mechanism (default port 7890, fallback 7891).
    """
    def __init__(self):
        self.base_url = os.getenv("UNITY_BRIDGE_URL", "http://localhost").rstrip("/")
        self.default_port = int(os.getenv("UNITY_BRIDGE_PORT", "7890"))
        self.fallback_port = int(os.getenv("UNITY_BRIDGE_FALLBACK_PORT", "7891"))
        self._active_port: Optional[int] = None
        self.client = httpx.AsyncClient(timeout=10.0)

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
                response = await self.client.get(test_url, timeout=2.0)
                if response.status_code == 200:
                    logger.info(f"Successfully connected to AnkleBreaker on port {port}")
                    self._active_port = port
                    return port
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
                logger.warning(f"AnkleBreaker not responding on port {port}")
                continue

        # If neither port responds, fallback to the default port and log a warning
        logger.error(
            f"AnkleBreaker is not reachable on ports {self.default_port} or {self.fallback_port}. "
            f"Defaulting to {self.default_port}."
        )
        self._active_port = self.default_port
        return self.default_port

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
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

    async def execute_code(self, code: str) -> Dict[str, Any]:
        """
        Sends C# or Editor script code to Unity to be dynamically compiled and executed.
        Returns a dictionary containing execution status, results, and logs.
        """
        response = await self._request("POST", "/api/editor/execute-code", json={"code": code})
        return response.json()

    async def set_play_mode(self, active: bool) -> Dict[str, Any]:
        """
        Sets the Unity Editor Play Mode state (active=True to play, active=False to stop).
        """
        response = await self._request("POST", "/api/editor/play-mode", json={"active": active})
        return response.json()

    async def save_scene(self) -> Dict[str, Any]:
        """
        Forces the Unity Editor to save the currently active scene.
        """
        response = await self._request("POST", "/api/scene/save")
        return response.json()

    async def get_compilation_errors(self) -> Dict[str, Any]:
        """
        Retrieves active compiler errors and warnings from the Unity project.
        """
        response = await self._request("GET", "/api/compilation/errors")
        return response.json()

    async def get_queue_status(self, ticket_id: str) -> Dict[str, Any]:
        """
        Checks the status of a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("GET", "/api/queue/status", params={"ticket_id": ticket_id})
        return response.json()

    async def close(self):
        """Closes the underlying HTTPX client."""
        await self.client.aclose()
