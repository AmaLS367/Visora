# Visora setup

## Prerequisites

- Python 3.10+ and `uv`
- Unity 2021.3 LTS or newer
- AnkleBreaker for the default legacy transport, or the bundled `com.visora.editor` package for native mode

## Unity bridge

### Legacy default

Install AnkleBreaker in the Unity project and start the Editor. Keep `UNITY_BRIDGE_MODE=legacy` (or omit it). Visora discovers configured ports and ignores native bridges in this mode.

### Native package

Install `unity-package` through Unity Package Manager or a local package path, then set `UNITY_BRIDGE_MODE=native`. The package listens only on `127.0.0.1` and `localhost`; its `/api/ping` response reports `flavor: "visora-native"` and version `1.1.0`.

Native mode includes typed camera endpoints and the same local statement-body C# executor used by `safe_transaction`. Compilation, runtime, and timeout failures return structured errors. `auto` is available for mixed installations but prefers legacy when both bridges respond.

## Configuration

```dotenv
UNITY_BRIDGE_URL=http://127.0.0.1
UNITY_BRIDGE_PORT=7890
UNITY_BRIDGE_FALLBACK_PORT=7891
UNITY_BRIDGE_PORTS_TO_SCAN=7890,7891,7892,7893
UNITY_BRIDGE_TIMEOUT_SECONDS=10
UNITY_BRIDGE_PING_TIMEOUT_SECONDS=2
UNITY_BRIDGE_EXECUTION_TIMEOUT_SECONDS=60
UNITY_BRIDGE_MAX_RETRIES=2
UNITY_BRIDGE_RETRY_BACKOFF=0.5
UNITY_BRIDGE_MODE=legacy
LOG_LEVEL=INFO
```

## MCP client

Run the server through `uv run visora` or `uv run -- python -m backend.server`. Configure the client command as `uv` with arguments `run`, `--directory`, `<absolute Visora path>`, `visora`.

## Verification and recovery

Call `get_bridge_status` to identify the selected port and flavor. For a busy editor, use `wait_for_editor_idle`. For an unreachable bridge, confirm that Unity is open and the configured mode matches the bridge flavor. The exact tool names and parameters are maintained in [AGENT_WORKFLOWS.md](AGENT_WORKFLOWS.md).
