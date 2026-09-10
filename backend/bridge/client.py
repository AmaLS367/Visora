import asyncio
import logging
import time
import uuid
from typing import Any

import httpx

from backend.bridge.exceptions import (
    BridgeBusyError,
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


def _looks_like_reload_body(response: httpx.Response) -> bool:
    """
    Whether a 200 response carries the empty / non-JSON body Unity returns mid-domain-reload.

    The HTTP listener answers before the managed side can serialise anything. A leading `{` or `[`
    means real content (a JSON array is still a genuine protocol error, not a reload artefact, and
    is left for `_decode_json` to reject); anything else is treated as a transient reload.
    """
    body = response.text.lstrip()
    return not body or body[0] not in "{["


class _MidReloadError(Exception):
    """Internal marker: the bridge answered, but in a way that means Unity is mid-reload."""


class UnityBridge:
    """
    HTTP Client bridge for AnkleBreaker Unity Editor plugin.
    Implements dynamic multi-port discovery, fallback, retry mechanics, and typed exceptions.
    """

    # Poll cadence while waiting for Unity to leave compilation / domain reload. Short enough to
    # catch a typical 2-5s reload almost as soon as it clears.
    _READY_POLL_INTERVAL_SECONDS: float = 0.3

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.unity_bridge_url
        self.default_port = self.settings.unity_bridge_port
        self.fallback_port = self.settings.unity_bridge_fallback_port
        self._active_port: int | None = None
        # Last port that actually served a request. Tried first on reconnect so a domain reload that
        # drops _active_port does not trigger a full multi-port rescan on the next call.
        self._last_good_port: int | None = None
        self._bridge_flavor: str | None = None
        self._supported_features: frozenset[str] | None = None
        self.client = httpx.AsyncClient(timeout=self.settings.unity_bridge_timeout_seconds)

    @property
    def candidate_ports(self) -> list[int]:
        """Ordered list of candidate ports to scan or connect to."""
        ports: list[int] = []
        # Priority 0: Last port that served a request (skips a full rescan after a reload drop)
        if self._last_good_port is not None:
            ports.append(self._last_good_port)
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
        unidentified_port: int | None = None
        for port in ports:
            test_url = f"{self.base_url}:{port}/api/ping"
            try:
                logger.debug(f"Pinging Unity Bridge on {test_url}...")
                response = await self.client.get(test_url, timeout=self.settings.unity_bridge_ping_timeout_seconds)
                if response.status_code == 200:
                    try:
                        data: dict[str, Any] = _decode_json(response)
                    except BridgeProtocolError:
                        # Mid-domain-reload Unity answers 200 with no usable body. The port is alive
                        # but the flavor is genuinely unknown, and defaulting it here would cache a
                        # native bridge as legacy for the lifetime of this client, silently disabling
                        # every native capability. Remember the port, decide the flavor later.
                        if unidentified_port is None:
                            unidentified_port = port
                        continue
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

        if unidentified_port is not None:
            # Usable for requests, but the flavor stays unresolved so it is probed again once Unity
            # finishes reloading rather than being frozen at a guess.
            self._active_port = unidentified_port
            self._bridge_flavor = None
            logger.info(
                "Unity Bridge on port %s answered without an identifiable flavor; will re-probe",
                unidentified_port,
            )
            return unidentified_port

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

    async def _probe_editor_state(self, port: int | None = None) -> dict[str, Any]:
        """
        One direct, un-retried editor-state read used by the reload-recovery loop.

        Bypasses `_request` entirely: it targets a single known port with a short timeout and never
        triggers recovery itself, so it cannot recurse and never pays a multi-port scan.
        """
        target = port or self._active_port or self._last_good_port
        if target is None:
            raise BridgeConnectionError(
                message="No known Unity bridge port to probe for editor state.",
                ports=self.candidate_ports,
            )
        url = f"{self.base_url}:{target}/api/editor/state"
        response = await self.client.request(
            "POST", url, timeout=self.settings.unity_bridge_state_probe_timeout_seconds
        )
        response.raise_for_status()
        state = _decode_json(response)
        self._active_port = target
        self._last_good_port = target
        return state

    def _busy_message(self, reason: str) -> str:
        waited = self.settings.unity_bridge_ready_wait_seconds
        descriptions = {
            "compiling": "is compiling scripts",
            "updating": "is importing assets",
            "reloading": "is finishing a domain reload and the bridge is briefly unavailable",
            "unreachable": "is not reachable",
        }
        if reason == "unreachable":
            return (
                "Unity Editor is not reachable on any configured port. "
                "Verify that the Unity Editor is running and the bridge package is active."
            )
        return (
            f"Unity Editor {descriptions.get(reason, 'is busy')} and did not settle within "
            f"{waited:.0f}s. This is usually transient - retry once the editor is idle."
        )

    async def _await_editor_recovery(self, *, triggered_by: Exception | None = None) -> None:
        """
        Polls Unity back to readiness after a request already failed with a reload signal.

        Called reactively - only once a real request hit a connection drop or a mid-reload body -
        so a healthy call never runs this. Pings only the last known-good port each iteration (one
        full rescan at most, in case the bridge genuinely moved), and raises BridgeBusyError with a
        `reason` if the editor stays busy past `unity_bridge_ready_wait_seconds`.
        """
        deadline = time.monotonic() + self.settings.unity_bridge_ready_wait_seconds
        known_port = self._active_port or self._last_good_port
        had_known_port = known_port is not None
        reason = "reloading" if had_known_port else "unreachable"
        last_error: Exception | None = triggered_by
        consecutive_probe_failures = 0
        did_full_rescan = False

        while True:
            try:
                state = await self._probe_editor_state(known_port)
                is_compiling = bool(state.get("isCompiling", False))
                is_updating = bool(state.get("isUpdating", False))
                if not is_compiling and not is_updating:
                    return
                reason = "compiling" if is_compiling else "updating"
                consecutive_probe_failures = 0
            except (BridgeConnectionError, BridgeTimeoutError, BridgeProtocolError, httpx.HTTPError) as exc:
                last_error = exc
                consecutive_probe_failures += 1
                reason = "reloading" if had_known_port else "unreachable"
                # Only perform a full candidate rescan if known_port is unknown or repeatedly failed
                # (at least 3 probes), so a normal 1-2s domain reload on the same port never burns
                # the ready_wait_seconds budget on candidate pings.
                if not did_full_rescan and (not had_known_port or consecutive_probe_failures >= 3):
                    did_full_rescan = True
                    try:
                        known_port = await self.get_active_port(force_refresh=True)
                        had_known_port = True
                        reason = "reloading"
                        consecutive_probe_failures = 0
                        continue
                    except BridgeConnectionError:
                        known_port = None

            if time.monotonic() >= deadline:
                raise BridgeBusyError(
                    message=self._busy_message(reason),
                    reason=reason,
                    retry_after_seconds=3.0 if reason != "unreachable" else None,
                ) from last_error

            await asyncio.sleep(self._READY_POLL_INTERVAL_SECONDS)

    async def _request(  # noqa: PLR0912, PLR0915
        self,
        method: str,
        path: str,
        *,
        recover: bool = True,
        retry_on_timeout: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Sends an HTTP request to the bridge on the active port, with retry and typed error mapping.

        No preemptive editor-state probe: a healthy call costs exactly one request. `recover=True`
        means that once a request fails with a connection drop or a mid-reload body, the bridge
        polls Unity back to readiness (`_await_editor_recovery`) and then retries the request once;
        callers whose own poll loop already handles transience (state / health / queue reads) pass
        `recover=False`. `retry_on_timeout=False` makes a read timeout fail immediately - the request
        already reached Unity, so replaying a non-idempotent call could apply it twice.
        """
        max_attempts = max(1, self.settings.unity_bridge_max_retries + 1)
        last_exception: Exception | None = None
        saw_reload_signal = False
        timeout_budget = kwargs.get("timeout", self.settings.unity_bridge_timeout_seconds)
        if isinstance(timeout_budget, httpx.Timeout):
            timeout_seconds = timeout_budget.read or self.settings.unity_bridge_timeout_seconds
        elif isinstance(timeout_budget, (int, float)):
            timeout_seconds = float(timeout_budget)
        else:
            timeout_seconds = self.settings.unity_bridge_timeout_seconds

        for attempt in range(max_attempts):
            try:
                port = await self.get_active_port(force_refresh=(attempt > 0 and self._active_port is None))
                url = f"{self.base_url}:{port}/{path.lstrip('/')}"
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                if recover and _looks_like_reload_body(response):
                    raise _MidReloadError
                self._last_good_port = port
                return response
            except httpx.HTTPStatusError as e:
                logger.error(f"Bridge HTTP status error {e.response.status_code} for {path}: {e}")
                raise BridgeHTTPError(
                    message=f"Bridge HTTP error {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code,
                    response_body=e.response.text,
                ) from e
            except _MidReloadError:
                logger.warning(f"Bridge answered with a mid-reload body for {path}; will wait for the editor")
                self._active_port = None
                last_exception = BridgeProtocolError(
                    message=f"Bridge returned an unusable body for '{path}' during a probable domain reload.",
                    status_code=200,
                )
                saw_reload_signal = True
                break
            except httpx.ReadTimeout as e:
                logger.warning(f"Bridge read timeout on attempt {attempt + 1}/{max_attempts} for {path}: {e}")
                last_exception = e
                if not retry_on_timeout:
                    break
            except (httpx.RequestError, BridgeConnectionError) as e:
                logger.warning(f"Bridge connection error on attempt {attempt + 1}/{max_attempts} for {path}: {e}")
                self._active_port = None
                last_exception = e
                # Hand over to recovery immediately when dropping from a known working port
                if recover and self._last_good_port is not None:
                    break

            if attempt < max_attempts - 1:
                await asyncio.sleep(self.settings.unity_bridge_retry_backoff * (attempt + 1))

        # A read timeout already reached Unity - never recover-and-resend (double-apply risk).
        if isinstance(last_exception, httpx.ReadTimeout):
            raise BridgeTimeoutError(
                message=f"Bridge request to '{path}' timed out after {timeout_seconds:.1f}s.",
                timeout_seconds=timeout_seconds,
            ) from last_exception

        connection_dropped = saw_reload_signal or isinstance(
            last_exception, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, BridgeConnectionError)
        )
        has_prior_connection = (self._last_good_port is not None) or saw_reload_signal
        if recover and connection_dropped and has_prior_connection:
            await self._await_editor_recovery(triggered_by=last_exception)
            return await self._request(method, path, recover=False, retry_on_timeout=retry_on_timeout, **kwargs)

        if isinstance(last_exception, httpx.ConnectTimeout):
            raise BridgeTimeoutError(
                message=f"Bridge request to '{path}' timed out after {timeout_seconds:.1f}s.",
                timeout_seconds=timeout_seconds,
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
            # Arbitrary C# with no idempotency key: a replay after a read timeout could double-apply
            # the edit, so a timed-out execute fails immediately rather than retrying.
            retry_on_timeout=False,
        )
        return _decode_json(response)

    async def execute_capability(
        self,
        legacy_code: str,
        *,
        native_path: str | None = None,
        native_payload: dict[str, Any] | None = None,
        retry_on_timeout: bool = True,
    ) -> dict[str, Any]:
        """Runs a capability through native HTTP when available, otherwise through the compatible executor."""
        if native_path is not None and await self.is_native_bridge():
            response = await self._request(
                "POST", native_path, json=native_payload or {}, retry_on_timeout=retry_on_timeout
            )
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
        # recover=False: wait_for_play_mode / wait_for_editor_ready poll this and handle transient
        # reload failures themselves; it must return or raise promptly, not block on recovery.
        response = await self._request("POST", "/api/editor/state", recover=False)
        return _decode_json(response)

    async def set_play_mode(self, active: bool) -> dict[str, Any]:
        """
        Sets the Unity Editor Play Mode state (active=True to play, active=False to stop).
        """
        response = await self._request(
            "POST",
            "/api/editor/play-mode",
            json={"action": "play" if active else "stop"},
            recover=False,
            retry_on_timeout=False,
        )
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
        response = await self._request("POST", "/api/scene/save", retry_on_timeout=False)
        return _decode_json(response)

    async def get_compilation_errors(self) -> dict[str, Any]:
        """
        Retrieves active compiler errors and warnings from the Unity project.
        """
        # recover=False: this read must stay answerable during a reload rather than block on it.
        response = await self._request("GET", "/api/compilation/errors", recover=False)
        return _decode_json(response)

    async def get_queue_status(self, ticket_id: str) -> dict[str, Any]:
        """
        Checks the status of a long-running ticket in the AnkleBreaker task queue.
        """
        # recover=False: queue polling has its own wait loop and must not stall on editor readiness.
        response = await self._request("GET", "/api/queue/status", params={"ticketId": ticket_id}, recover=False)
        return _decode_json(response)

    async def get_bridge_flavor(self, force_refresh: bool = False) -> str:
        """
        Returns the detected bridge flavor ('visora-native' or 'anklebreaker').
        """
        if self._bridge_flavor is None or force_refresh:
            await self.get_active_port(force_refresh=True)
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

        if self._supported_features is not None:
            return feature in self._supported_features

        if not await self.is_native_bridge():
            if self._bridge_flavor is not None:
                self._supported_features = frozenset()
            return False

        # Deliberately not get_bridge_info(): that synthesizes a legacy-shaped answer when the info
        # endpoint fails, and caching a synthesized answer would pin this client to the slow capture
        # path for its whole lifetime over one transient failure. An unanswered probe caches nothing.
        try:
            response = await self._request("GET", "/api/visora/info", recover=False)
            features = _decode_json(response).get("supportedFeatures", [])
        except Exception as exc:
            logger.warning("Bridge capabilities could not be read and were not cached: %s", exc)
            return False

        if not isinstance(features, list):
            logger.warning("Bridge reported capabilities in an unexpected shape and they were not cached")
            return False

        self._supported_features = frozenset(str(item) for item in features)
        return feature in self._supported_features

    async def get_bridge_info(self) -> dict[str, Any]:
        """
        Retrieves detailed information about the active bridge, Unity editor version, and supported features.
        """
        if await self.is_native_bridge():
            try:
                response = await self._request("GET", "/api/visora/info", recover=False)
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
        auto_frame: bool = False,
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
                "autoFrame": auto_frame,
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

    async def list_keyframes_native(
        self, clip_path: str, target_path: str, type_name: str, property_name: str
    ) -> dict[str, Any]:
        """Reads every key of one logical property via /api/visora/animation/keyframes/list."""
        response = await self._request(
            "POST",
            "/api/visora/animation/keyframes/list",
            json={
                "clipPath": clip_path,
                "targetPath": target_path,
                "typeName": type_name,
                "propertyName": property_name,
            },
        )
        return _decode_json(response)

    async def set_keyframe_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_path: str,
        type_name: str,
        property_name: str,
        time: float,
        values: list[float],
        tangent_mode: str | None,
        in_tangent: list[float] | None,
        out_tangent: list[float] | None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Upserts a keyframe across every resolved channel via /api/visora/animation/keyframes/set."""
        response = await self._request(
            "POST",
            "/api/visora/animation/keyframes/set",
            json={
                "clipPath": clip_path,
                "targetPath": target_path,
                "typeName": type_name,
                "propertyName": property_name,
                "time": time,
                "values": values,
                "tangentMode": tangent_mode,
                "inTangent": in_tangent,
                "outTangent": out_tangent,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def move_keyframe_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_path: str,
        type_name: str,
        property_name: str,
        from_time: float,
        to_time: float,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Moves an existing keyframe via /api/visora/animation/keyframes/move."""
        response = await self._request(
            "POST",
            "/api/visora/animation/keyframes/move",
            json={
                "clipPath": clip_path,
                "targetPath": target_path,
                "typeName": type_name,
                "propertyName": property_name,
                "fromTime": from_time,
                "toTime": to_time,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def remove_keyframe_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_path: str,
        type_name: str,
        property_name: str,
        time: float,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Removes an existing keyframe via /api/visora/animation/keyframes/remove."""
        response = await self._request(
            "POST",
            "/api/visora/animation/keyframes/remove",
            json={
                "clipPath": clip_path,
                "targetPath": target_path,
                "typeName": type_name,
                "propertyName": property_name,
                "time": time,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def hold_keyframe_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_path: str,
        type_name: str,
        property_name: str,
        time: float,
        hold_until: float,
        value: list[float] | None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Flattens a range via /api/visora/animation/keyframes/hold."""
        response = await self._request(
            "POST",
            "/api/visora/animation/keyframes/hold",
            json={
                "clipPath": clip_path,
                "targetPath": target_path,
                "typeName": type_name,
                "propertyName": property_name,
                "time": time,
                "holdUntil": hold_until,
                "value": value,
                "hasValue": value is not None,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def create_event_native(  # noqa: PLR0913
        self,
        clip_path: str,
        time: float,
        function_name: str,
        string_param: str,
        float_param: float,
        int_param: int,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Adds an AnimationEvent via /api/visora/animation/events/create."""
        response = await self._request(
            "POST",
            "/api/visora/animation/events/create",
            json={
                "clipPath": clip_path,
                "time": time,
                "functionName": function_name,
                "stringParam": string_param,
                "floatParam": float_param,
                "intParam": int_param,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def remove_event_native(
        self, clip_path: str, time: float, function_name: str | None, operation_id: str | None = None
    ) -> dict[str, Any]:
        """Removes matching AnimationEvents via /api/visora/animation/events/remove."""
        response = await self._request(
            "POST",
            "/api/visora/animation/events/remove",
            json={
                "clipPath": clip_path,
                "time": time,
                "functionName": function_name,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def list_backups_native(self, clip_path: str) -> dict[str, Any]:
        """Lists backups via /api/visora/animation/backups/list."""
        response = await self._request("POST", "/api/visora/animation/backups/list", json={"clipPath": clip_path})
        return _decode_json(response)

    async def restore_clip_native(
        self, clip_path: str, backup_id: str, operation_id: str | None = None
    ) -> dict[str, Any]:
        """Restores a backup via /api/visora/animation/backups/restore."""
        response = await self._request(
            "POST",
            "/api/visora/animation/backups/restore",
            json={
                "clipPath": clip_path,
                "backupId": backup_id,
                "operationId": operation_id or str(uuid.uuid4()),
            },
        )
        return _decode_json(response)

    async def begin_transaction_native(self, description: str = "Visora Agent Operation") -> dict[str, Any]:
        """Direct native scene transaction begin via /api/visora/transaction/begin."""
        response = await self._request(
            "POST", "/api/visora/transaction/begin", json={"description": description}, retry_on_timeout=False
        )
        return _decode_json(response)

    async def commit_transaction_native(self, transaction_id: str, save_scene: bool = False) -> dict[str, Any]:
        """Direct native scene transaction commit via /api/visora/transaction/commit."""
        response = await self._request(
            "POST",
            "/api/visora/transaction/commit",
            json={"transactionId": transaction_id, "saveScene": save_scene},
            retry_on_timeout=False,
        )
        return _decode_json(response)

    async def rollback_transaction_native(self, transaction_id: str) -> dict[str, Any]:
        """Direct native scene transaction rollback via /api/visora/transaction/rollback."""
        response = await self._request(
            "POST",
            "/api/visora/transaction/rollback",
            json={"transactionId": transaction_id},
            retry_on_timeout=False,
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
            retry_on_timeout=False,
        )
        return _decode_json(response)

    async def inspect_asset_native(self, asset_path: str) -> dict[str, Any]:
        """Direct native asset inspection via /api/visora/asset/inspect."""
        response = await self._request("POST", "/api/visora/asset/inspect", json={"assetPath": asset_path})
        return _decode_json(response)

    async def inspect_prefab_asset_native(self, asset_path: str, max_objects: int) -> dict[str, Any]:
        """
        Read-only Prefab asset inspection via /api/visora/prefab/inspect.

        `maxObjects` is sent to Unity rather than trimmed here on purpose: a deep Prefab can hold
        thousands of GameObjects, and capping on the Unity side keeps the whole response bounded
        instead of shipping a giant payload only to discard most of it.
        """
        response = await self._request(
            "POST",
            "/api/visora/prefab/inspect",
            json={"assetPath": asset_path, "maxObjects": max_objects},
        )
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
        response = await self._request("POST", "/api/visora/asset/instantiate", json=payload, retry_on_timeout=False)
        return _decode_json(response)

    async def validate_humanoid_avatar(
        self,
        target_path: str | None = None,
        asset_path: str | None = None,
    ) -> dict[str, Any]:
        """Direct native humanoid avatar validation via /api/visora/humanoid/validate."""
        payload: dict[str, Any] = {}
        if target_path:
            payload["targetPath"] = target_path
        if asset_path:
            payload["assetPath"] = asset_path
        response = await self._request("POST", "/api/visora/humanoid/validate", json=payload)
        return _decode_json(response)

    async def configure_humanoid_avatar(
        self,
        asset_path: str,
        bone_mapping_overrides: dict[str, str] | None = None,
        source_avatar_path: str | None = None,
    ) -> dict[str, Any]:
        """Direct native humanoid avatar configuration via /api/visora/humanoid/configure."""
        payload: dict[str, Any] = {"assetPath": asset_path}
        if source_avatar_path:
            payload["sourceAvatarPath"] = source_avatar_path
        if bone_mapping_overrides:
            payload["boneOverrideKeys"] = list(bone_mapping_overrides.keys())
            payload["boneOverrideValues"] = list(bone_mapping_overrides.values())
        response = await self._request("POST", "/api/visora/humanoid/configure", json=payload, retry_on_timeout=False)
        return _decode_json(response)

    async def analyze_contact_constraints(  # noqa: PLR0913
        self,
        target_path: str,
        clip_path: str,
        effectors: list[str] | None = None,
        ground_mode: str = "plane",
        ground_y: float = 0.0,
        vel_threshold: float = 0.05,
        height_tol: float = 0.05,
    ) -> dict[str, Any]:
        """Direct native contact analysis via /api/visora/humanoid/contact/analyze."""
        payload: dict[str, Any] = {
            "targetPath": target_path,
            "clipPath": clip_path,
            "effectors": effectors or ["left_foot", "right_foot"],
            "groundMode": ground_mode,
            "groundY": ground_y,
            "velThreshold": vel_threshold,
            "heightTol": height_tol,
        }
        response = await self._request("POST", "/api/visora/humanoid/contact/analyze", json=payload)
        return _decode_json(response)

    async def bake_contact_constraints(  # noqa: PLR0913
        self,
        target_path: str,
        clip_path: str,
        output_clip_path: str | None = None,
        effectors: list[str] | None = None,
        ground_y: float = 0.0,
        fix_sliding: bool = True,
        fix_penetration: bool = True,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Direct native contact IK baking via /api/visora/humanoid/contact/bake."""
        payload: dict[str, Any] = {
            "targetPath": target_path,
            "clipPath": clip_path,
            "outputClipPath": output_clip_path or "",
            "effectors": effectors or ["left_foot", "right_foot"],
            "groundY": ground_y,
            "fixSliding": fix_sliding,
            "fixPenetration": fix_penetration,
            "operationId": operation_id or "",
        }
        response = await self._request(
            "POST", "/api/visora/humanoid/contact/bake", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def solve_two_bone_ik_native(  # noqa: PLR0913
        self,
        target_path: str,
        target_position: list[float],
        effector: str | None = None,
        root_bone: str | None = None,
        mid_bone: str | None = None,
        end_bone: str | None = None,
        target_rotation: list[float] | None = None,
        pole_vector: list[float] | None = None,
        space: str = "world",
        camera_name: str = "Main Camera",
        weight: float = 1.0,
        apply_to_scene: bool = False,
        bake_to_clip: str | None = None,
        sample_time: float | None = None,
    ) -> dict[str, Any]:
        """Direct native Two-Bone IK solve via /api/visora/animation/ik/two-bone."""
        payload: dict[str, Any] = {
            "targetPath": target_path,
            "targetPosition": target_position,
            "effector": effector or "",
            "rootBone": root_bone or "",
            "midBone": mid_bone or "",
            "endBone": end_bone or "",
            "targetRotation": target_rotation or [],
            "poleVector": pole_vector or [],
            "space": space,
            "cameraName": camera_name,
            "weight": weight,
            "applyToScene": apply_to_scene,
            "bakeToClip": bake_to_clip or "",
            "sampleTime": sample_time if sample_time is not None else 0.0,
            "hasSampleTime": sample_time is not None,
        }
        response = await self._request(
            "POST", "/api/visora/animation/ik/two-bone", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def place_effector_in_viewport_native(  # noqa: PLR0913
        self,
        target_path: str,
        viewport_x: float,
        viewport_y: float,
        camera_depth: float,
        camera_name: str = "Main Camera",
        effector: str | None = None,
        root_bone: str | None = None,
        mid_bone: str | None = None,
        end_bone: str | None = None,
        align_mode: str = "face_camera",
        custom_rotation: list[float] | None = None,
        pole_vector: list[float] | None = None,
        weight: float = 1.0,
        apply_to_scene: bool = False,
        bake_to_clip: str | None = None,
        sample_time: float | None = None,
    ) -> dict[str, Any]:
        """Direct native viewport effector placement via /api/visora/animation/viewport-placement."""
        payload: dict[str, Any] = {
            "targetPath": target_path,
            "viewportX": viewport_x,
            "viewportY": viewport_y,
            "cameraDepth": camera_depth,
            "cameraName": camera_name,
            "effector": effector or "",
            "rootBone": root_bone or "",
            "midBone": mid_bone or "",
            "endBone": end_bone or "",
            "alignMode": align_mode,
            "customRotation": custom_rotation or [],
            "poleVector": pole_vector or [],
            "weight": weight,
            "applyToScene": apply_to_scene,
            "bakeToClip": bake_to_clip or "",
            "sampleTime": sample_time if sample_time is not None else 0.0,
            "hasSampleTime": sample_time is not None,
        }
        response = await self._request(
            "POST", "/api/visora/animation/viewport-placement", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def solve_character_gaze_native(  # noqa: PLR0913
        self,
        target_path: str,
        target_look_at_position: list[float] | None = None,
        target_transform_path: str | None = None,
        chest_weight: float = 0.15,
        neck_weight: float = 0.35,
        head_weight: float = 0.50,
        eyes_weight: float = 0.0,
        up_vector: list[float] | None = None,
        apply_to_scene: bool = False,
        bake_to_clip: str | None = None,
        sample_time: float | None = None,
    ) -> dict[str, Any]:
        """Direct native character gaze solving via /api/visora/animation/gaze/solve."""
        payload: dict[str, Any] = {
            "targetPath": target_path,
            "targetLookAtPosition": target_look_at_position or [],
            "targetTransformPath": target_transform_path or "",
            "chestWeight": chest_weight,
            "neckWeight": neck_weight,
            "headWeight": head_weight,
            "eyesWeight": eyes_weight,
            "upVector": up_vector or [],
            "applyToScene": apply_to_scene,
            "bakeToClip": bake_to_clip or "",
            "sampleTime": sample_time if sample_time is not None else 0.0,
            "hasSampleTime": sample_time is not None,
        }
        response = await self._request("POST", "/api/visora/animation/gaze/solve", json=payload, retry_on_timeout=False)
        return _decode_json(response)

    async def analyze_joint_motion_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_path: str,
        bones: list[str] | None = None,
        sample_fps: int = 60,
        jerk_threshold: float = 120.0,
        angular_jerk_threshold: float = 4000.0,
    ) -> dict[str, Any]:
        """Direct native motion derivative analysis via /api/visora/animation/qa/motion."""
        payload: dict[str, Any] = {
            "clipPath": clip_path,
            "targetPath": target_path,
            "bones": bones or [],
            "sampleFps": sample_fps,
            "jerkThreshold": jerk_threshold,
            "angularJerkThreshold": angular_jerk_threshold,
        }
        response = await self._request("POST", "/api/visora/animation/qa/motion", json=payload)
        return _decode_json(response)

    async def detect_curve_discontinuities_native(
        self,
        clip_path: str,
        filter_curves: list[str] | None = None,
        auto_fix: bool = False,
    ) -> dict[str, Any]:
        """Direct native curve discontinuity scanning via /api/visora/animation/qa/discontinuities."""
        payload: dict[str, Any] = {
            "clipPath": clip_path,
            "filterCurves": filter_curves or [],
            "autoFix": auto_fix,
        }
        response = await self._request(
            "POST", "/api/visora/animation/qa/discontinuities", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def execute_animation_transaction_native(
        self,
        operations: list[dict[str, Any]],
        transaction_id: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Direct native animation transaction execution via /api/visora/animation/transaction/execute."""
        payload: dict[str, Any] = {
            "transactionId": transaction_id or "",
            "description": description or "",
            "operations": operations,
        }
        response = await self._request(
            "POST", "/api/visora/animation/transaction/execute", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def bake_effector_contact_native(  # noqa: PLR0913
        self,
        clip_path: str,
        target_object_path: str,
        effector: str,
        target_type: str = "world_point",
        target_position: list[float] | None = None,
        scene_object_path: str | None = None,
        camera_name: str | None = None,
        viewport_coordinates: list[float] | None = None,
        viewport_depth: float = 0.5,
        time_range: list[float] | None = None,
        blend_in_seconds: float = 0.1,
        blend_out_seconds: float = 0.1,
        pole_vector: list[float] | None = None,
        target_rotation: list[float] | None = None,
    ) -> dict[str, Any]:
        """Direct native generalized effector contact baking via /api/visora/animation/contact/bake-effector."""
        payload: dict[str, Any] = {
            "clipPath": clip_path,
            "targetObjectPath": target_object_path,
            "effector": effector,
            "targetType": target_type,
            "targetPosition": target_position or [],
            "sceneObjectPath": scene_object_path or "",
            "cameraName": camera_name or "",
            "viewportCoordinates": viewport_coordinates or [0.5, 0.5],
            "viewportDepth": viewport_depth,
            # Empty list => C# falls back to the whole clip; never silently truncate to [0, 1].
            "timeRange": time_range if time_range is not None else [],
            "blendInSeconds": blend_in_seconds,
            "blendOutSeconds": blend_out_seconds,
            "poleVector": pole_vector or [],
            "targetRotation": target_rotation or [],
        }
        response = await self._request(
            "POST", "/api/visora/animation/contact/bake-effector", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def solve_camera_subject_contact_native(  # noqa: PLR0913
        self,
        character_path: str,
        character_clip_path: str,
        camera_name: str,
        camera_clip_path: str | None = None,
        effector: str = "right_foot",
        impact_time: float = 0.5,
        contact_duration: float = 0.2,
        lens_viewport: list[float] | None = None,
        lens_distance_meters: float = 0.3,
        hit_stop_duration: float = 0.08,
        camera_recoil_impulse: list[float] | None = None,
    ) -> dict[str, Any]:
        """Direct native camera-subject contact solving via /api/visora/animation/action/camera-subject-contact."""
        payload: dict[str, Any] = {
            "characterPath": character_path,
            "characterClipPath": character_clip_path,
            "cameraName": camera_name,
            "cameraClipPath": camera_clip_path or "",
            "effector": effector,
            "impactTime": impact_time,
            "contactDuration": contact_duration,
            "lensViewport": lens_viewport or [0.5, 0.5],
            "lensDistanceMeters": lens_distance_meters,
            "hitStopDuration": hit_stop_duration,
            "cameraRecoilImpulse": camera_recoil_impulse or [0.0, -0.15, -0.4],
        }
        response = await self._request(
            "POST", "/api/visora/animation/action/camera-subject-contact", json=payload, retry_on_timeout=False
        )
        return _decode_json(response)

    async def analyze_self_intersections_native(
        self,
        target_object_path: str,
        clip_path: str,
        sample_fps: int = 30,
        tolerance_meters: float = 0.02,
    ) -> dict[str, Any]:
        """Direct native self-intersection analysis via /api/visora/animation/intersections/analyze."""
        payload: dict[str, Any] = {
            "targetObjectPath": target_object_path,
            "clipPath": clip_path,
            "sampleFps": sample_fps,
            "toleranceMeters": tolerance_meters,
        }
        response = await self._request("POST", "/api/visora/animation/intersections/analyze", json=payload)
        return _decode_json(response)

    async def cancel_queue_ticket(self, ticket_id: str) -> dict[str, Any]:
        """
        Attempts to cancel a long-running ticket in the AnkleBreaker task queue.
        """
        response = await self._request("POST", "/api/queue/cancel", json={"ticketId": ticket_id}, recover=False)
        return _decode_json(response)

    async def close(self) -> None:
        """Closes the underlying HTTPX client."""
        await self.client.aclose()

    async def __aenter__(self) -> "UnityBridge":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
