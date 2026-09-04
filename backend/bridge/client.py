import asyncio
import logging
import time
from typing import Any

import httpx

from backend.bridge.exceptions import (
    BridgeConnectionError,
    BridgeHTTPError,
    BridgeProtocolError,
    BridgeTimeoutError,
)
from backend.config import Settings, get_settings

logger = logging.getLogger("backend.bridge")


def _decode_json(response: httpx.Response) -> dict[str, Any]:
    """
    Decodes a bridge response body into a JSON object.

    Every bridge call funnels through here so that a successful HTTP status carrying an unusable body
    becomes a typed BridgeProtocolError instead of a raw JSONDecodeError. Unity returns exactly that
    during a domain reload: the listener answers 200 before the managed side can serialise a payload.
    """
    body = response.text
    try:
        path = response.request.url.path
    except RuntimeError:
        path = "<unknown>"
    preview = body[:200]

    if not body.strip():
        raise BridgeProtocolError(
            message=f"Bridge returned an empty body for '{path}' with status {response.status_code}.",
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body_preview=preview,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise BridgeProtocolError(
            message=f"Bridge returned a non-JSON body for '{path}': {preview!r}",
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body_preview=preview,
        ) from exc

    if not isinstance(payload, dict):
        raise BridgeProtocolError(
            message=f"Bridge returned {type(payload).__name__} instead of a JSON object for '{path}'.",
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body_preview=preview,
        )

    return payload


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
        self._bridge_flavor: str | None = None
        self._supported_features: frozenset[str] | None = None
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
        native_candidate: tuple[int, str] | None = None
        for port in ports:
            test_url = f"{self.base_url}:{port}/api/ping"
            try:
                logger.debug(f"Pinging Unity Bridge on {test_url}...")
                response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
                if response.status_code == 200:
                    try:
                        data: dict[str, Any] = _decode_json(response)
                    except BridgeProtocolError:
                        # A bridge answering 200 with no usable body is mid-domain-reload; treat it
                        # as an unidentified flavor rather than letting discovery fail outright.
                        data = {}
                    flavor = data.get("flavor", "anklebreaker") if isinstance(data, dict) else "anklebreaker"
                    if not self._flavor_matches_mode(flavor):
                        logger.debug(
                            "Ignoring Unity Bridge flavor %s on port %s because UNITY_BRIDGE_MODE=%s",
                            flavor,
                            port,
                            self.settings.unity_bridge_mode,
                        )
                        continue
                    if self.settings.unity_bridge_mode == "auto" and flavor == "visora-native":
                        native_candidate = (port, flavor)
                        continue
                    self._bridge_flavor = flavor
                    logger.info("Successfully connected to Unity Bridge (%s) on port %s", flavor, port)
                    self._active_port = port
                    return port
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
                logger.debug(f"Unity Bridge not responding on port {port}")
                continue

        if native_candidate is not None:
            self._active_port, self._bridge_flavor = native_candidate
            logger.info(
                "Successfully connected to Unity Bridge (%s) on port %s",
                self._bridge_flavor,
                self._active_port,
            )
            return self._active_port

        msg = (
            f"No Unity bridge matching mode '{self.settings.unity_bridge_mode}' is reachable "
            f"on configured ports ({', '.join(str(p) for p in ports)})."
        )
        logger.error(msg)
        raise BridgeConnectionError(message=msg, ports=ports)

    def _flavor_matches_mode(self, flavor: str) -> bool:
        """Returns whether a detected bridge flavor is permitted by the configured transport mode."""
        if self.settings.unity_bridge_mode == "native":
            return flavor == "visora-native"
        if self.settings.unity_bridge_mode == "legacy":
            return flavor != "visora-native"
        return True

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
            except httpx.HTTPStatusError as e:
                logger.error(f"Bridge HTTP status error {e.response.status_code} for {path}: {e}")
                raise BridgeHTTPError(
                    message=f"Bridge HTTP error {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                ) from e
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.warning(f"Bridge timeout on attempt {attempt + 1}/{max_attempts}: {e}")
                last_exception = e
            except (httpx.RequestError, BridgeConnectionError) as e:
                logger.warning(f"Bridge connection error on attempt {attempt + 1}/{max_attempts}: {e}")
                self._active_port = None
                last_exception = e

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
        response = await self._request(
            "POST",
            "/api/editor/execute-code",
            json={"code": code, "timeoutSeconds": self.settings.unity_bridge_execution_timeout_seconds},
            timeout=self.settings.unity_bridge_execution_timeout_seconds,
        )
        return _decode_json(response)

    async def execute_capability(
        self,
        legacy_code: str,
        *,
        native_path: str | None = None,
        native_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Runs a capability through native HTTP when available, otherwise through the compatible executor."""
        if native_path is not None and await self.is_native_bridge():
            response = await self._request("POST", native_path, json=native_payload or {})
            return _decode_json(response)
        return await self.execute_code(legacy_code)

    async def render_camera(
        self,
        legacy_code: str,
        camera_name: str,
        width: int,
        height: int,
        image_format: str = "PNG",
    ) -> dict[str, Any]:
        """Renders through the native camera endpoint or the legacy-compatible executor."""
        return await self.execute_capability(
            legacy_code,
            native_path="/api/visora/camera/render",
            native_payload={"cameraName": camera_name, "width": width, "height": height, "format": image_format},
        )

    async def get_editor_state(self) -> dict[str, Any]:
        """Returns current Unity editor state including play mode, compilation, and active scene."""
        response = await self._request("POST", "/api/editor/state")
        return _decode_json(response)

    async def set_play_mode(self, active: bool) -> dict[str, Any]:
        """
        Sets the Unity Editor Play Mode state (active=True to play, active=False to stop).
        """
        response = await self._request("POST", "/api/editor/play-mode", json={"action": "play" if active else "stop"})
        return _decode_json(response)

    async def wait_for_play_mode(
        self,
        target_playing: bool,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """
        Polls get_editor_state until isPlaying matches target_playing and the editor is not compiling or updating.
        Retries through temporary bridge connection drops (e.g. during Unity domain reloads).
        """
        start = time.perf_counter()
        deadline = start + timeout_seconds
        last_state: dict[str, Any] | None = None
        last_error: Exception | None = None

        while time.perf_counter() < deadline:
            try:
                state = await self.get_editor_state()
                last_state = state
                is_playing = bool(state.get("isPlaying", False))
                is_compiling = bool(state.get("isCompiling", False))
                is_updating = bool(state.get("isUpdating", False))

                if is_playing == target_playing and not is_compiling and not is_updating:
                    return state
            except (BridgeConnectionError, BridgeTimeoutError, BridgeProtocolError, httpx.RequestError) as exc:
                last_error = exc
                logger.debug(
                    "Bridge temporarily unavailable while waiting for play mode %s: %s",
                    target_playing,
                    exc,
                )

            await asyncio.sleep(poll_interval_seconds)

        elapsed = time.perf_counter() - start
        mode_str = "Play Mode" if target_playing else "Edit Mode"
        state_str = f"last state: {last_state}" if last_state is not None else f"last error: {last_error}"
        raise BridgeTimeoutError(
            message=f"Timed out after {elapsed:.1f}s waiting for Unity to enter {mode_str} ({state_str}).",
            timeout_seconds=timeout_seconds,
        )

    async def wait_for_editor_ready(
        self,
        timeout_seconds: float = 15.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """
        Waits until the Unity bridge is reachable and the editor is idle (not compiling and not updating).
        """
        start = time.perf_counter()
        deadline = start + timeout_seconds
        last_state: dict[str, Any] | None = None
        last_error: Exception | None = None

        while time.perf_counter() < deadline:
            try:
                state = await self.get_editor_state()
                last_state = state
                is_compiling = bool(state.get("isCompiling", False))
                is_updating = bool(state.get("isUpdating", False))

                if not is_compiling and not is_updating:
                    return state
            except (BridgeConnectionError, BridgeTimeoutError, BridgeProtocolError, httpx.RequestError) as exc:
                last_error = exc
                logger.debug("Bridge not yet ready (attempting retry): %s", exc)

            await asyncio.sleep(poll_interval_seconds)

        elapsed = time.perf_counter() - start
        state_str = f"last state: {last_state}" if last_state is not None else f"last error: {last_error}"
        raise BridgeTimeoutError(
            message=f"Timed out after {elapsed:.1f}s waiting for Unity editor to become ready ({state_str}).",
            timeout_seconds=timeout_seconds,
        )

    async def save_scene(self) -> dict[str, Any]:
        """
        Forces the Unity Editor to save the currently active scene.
        """
        response = await self._request("POST", "/api/scene/save")
        return _decode_json(response)

    async def get_compilation_errors(self) -> dict[str, Any]:
        """
        Retrieves active compiler errors and warnings from the Unity project.
        """
        response = await self._request("GET", "/api/compilation/errors")
        return _decode_json(response)

    async def get_queue_status(self, ticket_id: str) -> dict[str, Any]:
        """
        Checks the status of a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("GET", "/api/queue/status", params={"ticketId": ticket_id})
        return _decode_json(response)

    async def get_bridge_flavor(self, force_refresh: bool = False) -> str:
        """
        Returns the detected bridge flavor ('visora-native' or 'anklebreaker').
        """
        if self._bridge_flavor is None or force_refresh:
            await self.get_active_port(force_refresh=force_refresh)
        return self._bridge_flavor or "anklebreaker"

    async def is_native_bridge(self, force_refresh: bool = False) -> bool:
        """
        Returns True if connected to the dedicated Visora native Unity package.
        """
        if self.settings.unity_bridge_mode == "legacy":
            return False
        flavor = await self.get_bridge_flavor(force_refresh=force_refresh)
        return flavor == "visora-native"

    async def supports_feature(self, feature: str, force_refresh: bool = False) -> bool:
        """
        Reports whether the connected bridge advertises a named capability.

        Checking the flavor alone is not enough: an older Visora package serves the same endpoint
        paths with different semantics, so a capability has to be advertised before it is used.
        """
        if force_refresh:
            self._supported_features = None

        if self._supported_features is None:
            if not await self.is_native_bridge():
                self._supported_features = frozenset()
            else:
                try:
                    info = await self.get_bridge_info()
                    features = info.get("supportedFeatures", [])
                    self._supported_features = (
                        frozenset(str(item) for item in features) if isinstance(features, list) else frozenset()
                    )
                except Exception as exc:
                    logger.warning("Could not read bridge capabilities, assuming none: %s", exc)
                    return False

        return feature in self._supported_features

    async def get_bridge_info(self) -> dict[str, Any]:
        """
        Retrieves detailed information about the active bridge, Unity editor version, and supported features.
        """
        if await self.is_native_bridge():
            try:
                response = await self._request("GET", "/api/visora/info")
                return _decode_json(response)
            except Exception as e:
                logger.warning(f"Failed to fetch native bridge info, falling back: {e}")

        # Fallback synthesis for AnkleBreaker bridge
        state = await self.get_editor_state()
        return {
            "success": True,
            "flavor": "anklebreaker",
            "version": "legacy",
            "unityVersion": "unknown",
            "isPlaying": state.get("isPlaying", False),
            "isCompiling": state.get("isCompiling", False),
            "activeScene": state.get("activeSceneName", ""),
            "supportedFeatures": [
                "execute_code",
                "editor_state",
                "play_mode",
                "save_scene",
                "compilation_errors",
                "task_queue",
            ],
        }

    async def render_camera_native(
        self,
        camera_name: str = "Main Camera",
        width: int = 1920,
        height: int = 1080,
        image_format: str = "PNG",
    ) -> dict[str, Any]:
        """Direct native high-performance camera render via /api/visora/camera/render."""
        response = await self._request(
            "POST",
            "/api/visora/camera/render",
            json={"cameraName": camera_name, "width": width, "height": height, "format": image_format},
        )
        return _decode_json(response)

    def _sequence_timeout(self, frame_count: int, interval: float) -> float:
        """
        Budget for a native sequence request, which stays open for the whole recording.

        Unity records across real editor time, so the response cannot arrive before the capture ends;
        the default per-request timeout would abort a recording that is working correctly.
        """
        recording_seconds = max(0.0, frame_count * max(0.0, interval))
        render_seconds = frame_count * 0.5
        return max(self.settings.unity_bridge_timeout_seconds, recording_seconds + render_seconds + 15.0)

    async def capture_sequence_native(
        self,
        camera_name: str = "Main Camera",
        width: int = 1280,
        height: int = 720,
        frame_count: int = 10,
        interval: float = 0.1,
    ) -> dict[str, Any]:
        """Direct native sequence capture via /api/visora/camera/sequence."""
        response = await self._request(
            "POST",
            "/api/visora/camera/sequence",
            json={
                "cameraName": camera_name,
                "width": width,
                "height": height,
                "frameCount": frame_count,
                "frameIntervalSeconds": interval,
            },
            timeout=self._sequence_timeout(frame_count, interval),
        )
        return _decode_json(response)

    async def capture_diagnostic_native(
        self,
        subject_path: str | None = None,
        width: int = 1280,
        height: int = 720,
    ) -> dict[str, Any]:
        """Single diagnostic_lit frame via /api/visora/camera/diagnostic."""
        response = await self._request(
            "POST",
            "/api/visora/camera/diagnostic",
            json={"subjectPath": subject_path or "", "width": width, "height": height},
        )
        return _decode_json(response)

    async def capture_diagnostic_sequence_native(
        self,
        subject_path: str | None = None,
        width: int = 1280,
        height: int = 720,
        frame_count: int = 10,
        interval: float = 0.1,
    ) -> dict[str, Any]:
        """Diagnostic_lit sequence via /api/visora/camera/diagnostic-sequence, built on one temporary rig."""
        response = await self._request(
            "POST",
            "/api/visora/camera/diagnostic-sequence",
            json={
                "subjectPath": subject_path or "",
                "width": width,
                "height": height,
                "frameCount": frame_count,
                "frameIntervalSeconds": interval,
            },
            timeout=self._sequence_timeout(frame_count, interval),
        )
        return _decode_json(response)

    async def preview_animation_sequence_native(  # noqa: PLR0913
        self,
        camera_name: str,
        clip_path: str,
        target_object_path: str,
        width: int = 640,
        height: int = 360,
        frame_count: int = 24,
        fps: float = 24.0,
        start_time: float = 0.0,
        end_time: float = 0.0,
    ) -> dict[str, Any]:
        """Deterministic Edit Mode clip preview via /api/visora/animation/preview-sequence."""
        response = await self._request(
            "POST",
            "/api/visora/animation/preview-sequence",
            json={
                "cameraName": camera_name,
                "clipPath": clip_path,
                "targetObjectPath": target_object_path,
                "width": width,
                "height": height,
                "frameCount": frame_count,
                "fps": fps,
                "startTime": start_time,
                "endTime": end_time,
            },
            timeout=self._sequence_timeout(frame_count, 1.0 / fps if fps > 0 else 0.0),
        )
        return _decode_json(response)

    async def diagnose_mesh_native(self, target_name: str = "") -> dict[str, Any]:
        """Direct native mesh diagnostics via /api/visora/mesh/diagnose."""
        response = await self._request("POST", "/api/visora/mesh/diagnose", json={"targetName": target_name})
        return _decode_json(response)

    async def diagnose_skeleton_native(self, root_object_name: str = "", search_query: str = "") -> dict[str, Any]:
        """Direct native skeleton diagnostics via /api/visora/skeleton/diagnose."""
        response = await self._request(
            "POST",
            "/api/visora/skeleton/diagnose",
            json={"rootObjectName": root_object_name, "searchQuery": search_query},
        )
        return _decode_json(response)

    async def inspect_clip_native(self, clip_name: str) -> dict[str, Any]:
        """Direct native AnimationClip curve inspection via /api/visora/animation/inspect."""
        response = await self._request("POST", "/api/visora/animation/inspect", json={"clipName": clip_name})
        return _decode_json(response)

    async def sample_clip_native(self, clip_name: str, target_object_name: str, sample_time: float) -> dict[str, Any]:
        """Direct native AnimationClip sampling via /api/visora/animation/sample."""
        response = await self._request(
            "POST",
            "/api/visora/animation/sample",
            json={"clipName": clip_name, "targetObjectName": target_object_name, "sampleTime": sample_time},
        )
        return _decode_json(response)

    async def begin_transaction_native(self, description: str = "Visora Agent Operation") -> dict[str, Any]:
        """Direct native scene transaction begin via /api/visora/transaction/begin."""
        response = await self._request("POST", "/api/visora/transaction/begin", json={"description": description})
        return _decode_json(response)

    async def commit_transaction_native(self, transaction_id: str, save_scene: bool = False) -> dict[str, Any]:
        """Direct native scene transaction commit via /api/visora/transaction/commit."""
        response = await self._request(
            "POST",
            "/api/visora/transaction/commit",
            json={"transactionId": transaction_id, "saveScene": save_scene},
        )
        return _decode_json(response)

    async def rollback_transaction_native(self, transaction_id: str) -> dict[str, Any]:
        """Direct native scene transaction rollback via /api/visora/transaction/rollback."""
        response = await self._request(
            "POST",
            "/api/visora/transaction/rollback",
            json={"transactionId": transaction_id},
        )
        return _decode_json(response)

    async def get_project_paths_native(self) -> dict[str, Any]:
        """Direct native project path query via /api/visora/asset/paths."""
        response = await self._request("GET", "/api/visora/asset/paths")
        return _decode_json(response)

    async def import_asset_native(self, asset_path: str, allow_unitypackage: bool = False) -> dict[str, Any]:
        """Direct native asset import via /api/visora/asset/import."""
        response = await self._request(
            "POST",
            "/api/visora/asset/import",
            json={"assetPath": asset_path, "allowUnityPackage": allow_unitypackage},
        )
        return _decode_json(response)

    async def inspect_asset_native(self, asset_path: str) -> dict[str, Any]:
        """Direct native asset inspection via /api/visora/asset/inspect."""
        response = await self._request("POST", "/api/visora/asset/inspect", json={"assetPath": asset_path})
        return _decode_json(response)

    async def instantiate_asset_native(  # noqa: PLR0913
        self,
        asset_path: str,
        parent_path: str | None = None,
        position: list[float] | None = None,
        rotation: list[float] | None = None,
        scale: list[float] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Direct native asset instantiation via /api/visora/asset/instantiate."""
        payload: dict[str, Any] = {
            "assetPath": asset_path,
            "parentPath": parent_path or "",
            "position": position or [0.0, 0.0, 0.0],
            "rotation": rotation or [0.0, 0.0, 0.0],
            "scale": scale or [1.0, 1.0, 1.0],
            "name": name or "",
        }
        response = await self._request("POST", "/api/visora/asset/instantiate", json=payload)
        return _decode_json(response)

    async def cancel_queue_ticket(self, ticket_id: str) -> dict[str, Any]:
        """
        Attempts to cancel a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("POST", "/api/queue/cancel", json={"ticketId": ticket_id})
        return _decode_json(response)

    async def close(self) -> None:
        """Closes the underlying HTTPX client."""
        await self.client.aclose()

    async def __aenter__(self) -> "UnityBridge":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
