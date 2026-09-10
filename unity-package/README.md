# Visora Editor Bridge (`com.visora.editor`)

The Visora Editor Bridge is the native Unity companion for the Visora Python MCP server. It runs inside Unity Editor, exposes local HTTP/JSON endpoints, moves Unity API work onto the Editor main thread, and implements high-performance camera, diagnostic, animation, transaction, and asset workflows.

It is not an MCP server by itself. The MCP client launches the Python `visora` process, which connects to this package over HTTP.

<p align="center">
  <img src="../docs/assets/native-unity-runtime.jpg" alt="A loopback router and serialized main-thread queue connect native camera, animation, mesh, asset, and transaction services around a Unity scene" width="100%">
</p>
<p align="center"><em>The native package keeps HTTP handling local and Unity API work on the Editor main thread.</em></p>

## Requirements

- Unity 6 (`6000.0`) or newer, as declared by `package.json`.
- Visora Python server configured with `UNITY_BRIDGE_MODE=native`.
- A local connection to the configured bridge port, `7890` by default.

The current package version is `1.2.0`. Python and Unity package versions are independent.

## Installation

### Unity Package Manager Git URL

1. Open **Window > Package Manager**.
2. Select **+ > Add package from git URL…**.
3. Enter:

   ```text
   https://github.com/AmaLS367/Visora.git?path=unity-package
   ```

Pin a Git tag or commit in production if you require reproducible package resolution.

### Local path

For development, add the package from disk or edit the Unity project’s `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.visora.editor": "file:../../Visora/unity-package"
  }
}
```

Wait for Unity package import and script compilation to finish before starting the MCP workflow.

## Configure the server

Open **Window > Visora > Server Monitor** to view and change:

- running/stopped status;
- active port;
- auto-start behavior;
- verbose logging.

The package auto-starts on port `7890` by default. It listens only on:

```text
http://127.0.0.1:<port>/
http://localhost:<port>/
```

The listener has no authentication and must not be changed to a public network bind without adding an appropriate security layer.

Configure the Python process to match:

```dotenv
UNITY_BRIDGE_MODE=native
UNITY_BRIDGE_URL=http://127.0.0.1
UNITY_BRIDGE_PORT=7890
```

## Verify

From the MCP client:

1. Call `get_bridge_status(scan_all_ports=true)`.
2. Confirm the active port matches Server Monitor.
3. Call `get_editor_state(wait=true)`.
4. Call `list_scene_cameras`, then a small `screenshot`.

For low-level local diagnosis, `GET /api/ping` returns the `visora-native` flavor and package version. `GET /api/visora/info` returns Unity state, API version, and advertised features.

## Architecture

- `Editor/Core/VisoraServer.cs` owns the loopback `HttpListener` and reload lifecycle.
- `Editor/Core/VisoraHttpRouter.cs` owns route DTOs, dispatch, and structured responses.
- `Editor/Core/MainThreadDispatcher.cs` serializes Unity API work onto Editor updates.
- `Editor/Services/` contains domain implementations.
- `Tests/Editor/` contains Unity EditMode integration tests.

HTTP handlers run on worker tasks, but nearly all Unity APIs are main-thread-only. Route implementations must use the dispatcher. Time-based render and sampling routines are stepped across Editor updates and serialized to prevent temporary animation/render state from interleaving.

The package also implements the stable AnkleBreaker-compatible core routes used by the Python bridge. This external HTTP/JSON compatibility does not imply internal C# or Python compatibility aliases.

## Feature groups

- Camera rendering, diagnostic lighting, inventory, projection, framing, and timed sequences.
- Editor task queue with ticket status and cancellation.
- Scene state, saving, Undo-aware transactions, and compilation diagnostics.
- Mesh, skeleton, AnimationClip, motion, discontinuity, contact, and self-intersection diagnostics.
- Animation sampling, preview, keyframe/event authoring, backups, and multi-operation transactions.
- Humanoid validation/configuration, contact baking, Two-Bone IK, viewport placement, gaze, and camera-subject action.
- Asset project paths, import, inspection, and Undo-aware instantiation.
- Statement-body code execution for the compatible escape-hatch workflow.

The authoritative capability names are returned by `/api/visora/info`; the Python client checks them for version-sensitive optimized and native-only behavior.

## Development and validation

After every change under `unity-package/`, run from the repository root:

```bash
uv run python scripts/check_unity_package.py
uv run python scripts/check_unity_package.py --format
```

After animation-stack changes, also run:

```bash
uv run python scripts/check_unity_tests.py
```

The compile gate requires the .NET SDK and real Unity managed assemblies. Use `VISORA_UNITY_MANAGED_DIR` when Unity is installed in a non-standard location. The EditMode runner uses `VISORA_UNITY_EDITOR` when it cannot auto-discover the executable and writes results/logs under `artifacts/`.

See the repository [setup guide](../docs/SETUP_GUIDE.md), [backend architecture](../docs/backend/README.md), and [bridge semantics](../docs/backend/BRIDGE.md) for the complete system behavior.
