# Visora setup and operations

This guide installs the Python MCP server, connects it to a Unity bridge, configures an MCP client, verifies the first connection, and explains common recovery paths.

## Supported components

Visora has two independently versioned components:

| Component | Current repository version | Requirement |
| --- | --- | --- |
| Python distribution `visora` | `0.1.3` | Python 3.10+ |
| Native Unity package `com.visora.editor` | `1.2.0` | Unity 6 (`6000.0`) or newer |

The Python backend can also use AnkleBreaker in legacy compatibility mode. Unity-version support for that path is determined by the installed AnkleBreaker version, not by the native package manifest.

<p align="center">
  <img src="assets/system-architecture.jpg" alt="A stdio MCP client connects to the Visora Python server, resilient HTTP bridge, and Unity Editor" width="100%">
</p>
<p align="center"><em>The MCP client talks to Python over stdio; Python talks to Unity over local HTTP.</em></p>

You need:

- one MCP client that can launch a stdio server;
- the Visora Python package or repository;
- one running Unity Editor with either the bundled native package or AnkleBreaker;
- network access only for online asset search/download features.

## 1. Install the Python server

### Published package

```bash
uv tool install visora
visora
```

Use this when you only need the Python server and will install the Unity package separately from Git.

Upgrade or remove the installed command with `uv tool upgrade visora` or `uv tool uninstall visora`.

### Repository development install

Install `uv`, then:

```bash
git clone https://github.com/AmaLS367/Visora.git
cd Visora
uv sync --locked --all-extras
```

Run with:

```bash
uv run visora
```

The equivalent module command is:

```bash
uv run python -m backend.server
```

The process uses stdio for MCP. When run manually it normally waits silently for protocol input; it does not open a web UI or MCP HTTP port.

## 2. Install a Unity bridge

Choose one stable configuration. Running both is supported through `auto`, but makes port and flavor mistakes harder to notice.

### Native package: recommended for the complete feature set

The current native package requires Unity 6.

In Unity Editor:

1. Open **Window > Package Manager**.
2. Select **+ > Add package from git URL…**.
3. Enter:

   ```text
   https://github.com/AmaLS367/Visora.git?path=unity-package
   ```

For local Visora development, add the package by disk path or add it to the Unity project’s `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.visora.editor": "file:../../Visora/unity-package"
  }
}
```

Open **Window > Visora > Server Monitor**. The native server auto-starts by default on port `7890` and listens only on `127.0.0.1`/`localhost`. Set:

```dotenv
UNITY_BRIDGE_MODE=native
UNITY_BRIDGE_PORT=7890
```

The ping response identifies `flavor: "visora-native"`, version `1.2.0`. The information endpoint advertises the supported feature set; Python uses those names for version-sensitive optimized and native-only workflows.

### Legacy AnkleBreaker bridge

Install and start AnkleBreaker in the Unity project according to that project’s instructions. Keep:

```dotenv
UNITY_BRIDGE_MODE=legacy
```

This is the Python default. Visora ignores a responding native bridge in legacy mode and executes compatible operations through the legacy HTTP contract and centralized C# statement bodies.

### Auto mode

```dotenv
UNITY_BRIDGE_MODE=auto
```

Auto accepts both bridge flavors and currently prefers legacy if both answer. Use it for migration or mixed environments, not to avoid choosing a known production configuration.

## 3. Configure the environment

For repository execution:

```bash
cp .env.example .env
```

Pydantic settings load `.env` relative to the server process working directory. If an MCP client launches Visora from another directory, either use its `--directory` option as shown below or supply settings in the client’s `env` object.

Comma-separated list settings use plain values:

```dotenv
UNITY_BRIDGE_PORTS_TO_SCAN=7890,7891,7892,7893
SEARXNG_INSTANCE_URLS=https://one.example,https://two.example
```

JSON arrays are accepted for bridge ports for transport compatibility, but the documented format is comma-separated.

## 4. Configure an MCP client

The exact settings UI varies by client, but the stdio command model is the same.

### Run from a cloned repository

```json
{
  "mcpServers": {
    "visora": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/Visora",
        "visora"
      ],
      "env": {
        "UNITY_BRIDGE_MODE": "native",
        "UNITY_BRIDGE_URL": "http://127.0.0.1"
      }
    }
  }
}
```

### Run an installed package

```json
{
  "mcpServers": {
    "visora": {
      "command": "visora",
      "args": [],
      "env": {
        "UNITY_BRIDGE_MODE": "native"
      }
    }
  }
}
```

If the client cannot find `uv` or `visora`, use the executable’s absolute path. Restart or reload the MCP client after changing its configuration.

Do not put provider credentials in a shared repository configuration. Prefer the client’s secret/environment mechanism or a local untracked `.env`.

## 5. Verify the connection

Open the Unity project and wait for compilation to finish. From the connected MCP client:

1. Call `get_bridge_status(scan_all_ports=true)`.
2. Confirm `connected=true`, the expected `active_port`, and reasonable latency.
3. Call `get_editor_state(wait=true)`.
4. Confirm `success=true`, `is_idle=true`, and the expected active scene.
5. Call `list_scene_cameras`.
6. Call `screenshot` with a small resolution such as 640×360.

The current status result reports connectivity, port, latency, and editor state; it does not expose the detected bridge flavor directly. With native mode, confirm the matching port in **Window > Visora > Server Monitor** when diagnosing configuration.

Do not use a scene mutation as the first connectivity test.

## Configuration reference

### Bridge and runtime

| Variable | Default | Meaning |
| --- | --- | --- |
| `UNITY_BRIDGE_URL` | `http://127.0.0.1` | Host/scheme without port; trailing slashes are removed |
| `UNITY_BRIDGE_PORT` | `7890` | First configured port |
| `UNITY_BRIDGE_FALLBACK_PORT` | `7891` | Second configured port |
| `UNITY_BRIDGE_PORTS_TO_SCAN` | `7890,7891,7892,7893` | Additional ordered candidates, de-duplicated |
| `UNITY_BRIDGE_MODE` | `legacy` | `legacy`, `native`, or `auto` |
| `UNITY_BRIDGE_TIMEOUT_SECONDS` | `10` | General HTTP request timeout |
| `UNITY_BRIDGE_PING_TIMEOUT_SECONDS` | `2` | One discovery ping timeout |
| `UNITY_BRIDGE_EXECUTION_TIMEOUT_SECONDS` | `60` | Dynamic C# execution timeout |
| `UNITY_BRIDGE_MAX_RETRIES` | `2` | Additional retry attempts where replay is allowed |
| `UNITY_BRIDGE_RETRY_BACKOFF` | `0.5` | Linear backoff base in seconds |
| `UNITY_BRIDGE_STATE_PROBE_TIMEOUT_SECONDS` | `2` | One reload-recovery state probe timeout |
| `UNITY_BRIDGE_READY_WAIT_SECONDS` | `8` | Total reactive wait for Unity to settle |
| `LOG_LEVEL` | `INFO` | Python log level |
| `COMPACT_TOOL_DEFINITIONS` | `true` | Remove redundant schema/doc detail from the advertised MCP catalog |
| `COMPACT_TOOL_RESULTS` | `true` | Remove duplicate/null result content from MCP responses |

### Visual and diagnostic bounds

| Variable | Default | Meaning |
| --- | ---: | --- |
| `VISION_INLINE_MAX_DIMENSION` | `1280` | Longest edge of inline images; full artifact remains on disk |
| `DIAGNOSTIC_MAX_BINDINGS` | `12` | Default clip binding sample bound |
| `DIAGNOSTIC_MAX_TRANSFORMS` | `12` | Default sampled transform bound |
| `DIAGNOSTIC_MAX_BONES` | `16` | Default skeleton output bound |
| `DIAGNOSTIC_MAX_BONE_BINDINGS` | `16` | Default mesh binding output bound |
| `DIAGNOSTIC_MAX_HIERARCHY_NODES` | `24` | Default imported hierarchy output bound |

### Asset search, download, and import

| Variable | Default | Meaning |
| --- | --- | --- |
| `SKETCHFAB_API_TOKEN` | empty | Required to resolve downloadable Sketchfab archives |
| `POLY_PIZZA_API_KEY` | empty | Enables Poly Pizza search/download |
| `DEFAULT_ASSET_IMPORT_DIR` | `Assets/VisoraDownloads` | Default destination inside the Unity project |
| `ASSET_DOWNLOAD_TIMEOUT_SECONDS` | `120` | Download request timeout |
| `MAX_ASSET_DOWNLOAD_SIZE_BYTES` | `250000000` | Streamed download ceiling |
| `ASSET_CACHE_DIR` | `.visora_cache` | Quarantine directory; must be outside `Assets` |
| `MAX_ASSET_ARCHIVE_ENTRIES` | `10000` | ZIP entry ceiling |
| `MAX_ASSET_ARCHIVE_UNCOMPRESSED_SIZE_BYTES` | `1000000000` | Total extracted-size ceiling |
| `MAX_ASSET_ARCHIVE_ENTRY_SIZE_BYTES` | `250000000` | One extracted-entry ceiling |
| `MAX_ASSET_ARCHIVE_COMPRESSION_RATIO` | `100` | Per-entry expansion ratio ceiling |
| `SEARXNG_INSTANCE_URLS` | public fallback list | Ordered comma-separated instances for `web_search_assets` |
| `WEB_SEARCH_TIMEOUT_SECONDS` | `10` | Web-search request timeout |

See [Asset pipeline](backend/ASSET_PIPELINE.md) before changing the security limits.

## Docker

The production image is multi-stage and installs a locked, non-editable environment. It runs as the unprivileged `visora` user (UID/GID `10001`) and exposes no MCP HTTP port because the client still communicates over stdio.

Build and run interactively:

```bash
docker compose build --pull
docker compose run --rm -i visora
```

The Compose service:

- uses a read-only root filesystem;
- drops all Linux capabilities;
- prevents privilege escalation;
- provides a small no-exec `/tmp` tmpfs;
- mounts only the `visora-cache` volume at `/data/cache`;
- maps `host.docker.internal` to the host gateway on Linux;
- passes the centralized bridge, diagnostic, compaction, and asset settings at runtime rather than copying `.env` into the image.

By default the container connects to `http://host.docker.internal:7890`. The native Unity bridge binds only to host loopback, which is not always reachable through the gateway on Linux. In that case use host networking explicitly:

```bash
docker run --rm -i --network host \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -e UNITY_BRIDGE_URL=http://127.0.0.1 \
  -e UNITY_BRIDGE_MODE=native \
  -v visora-cache:/data/cache \
  visora:0.1.3
```

Do not mount the Docker socket or the entire Unity project into the Visora container. The server normally needs only outbound HTTP access to the bridge and a cache/artifact persistence strategy appropriate for your client.

Remember that artifact paths returned from a container refer to its filesystem. Add a dedicated artifact volume if the MCP client must open those files on the host.

## Agent skills

`skills/` contains optional, detailed workflow packages. The MCP server already sends a short always-on set of critical instructions from `backend/app.py`; skills add task-specific sequencing and acceptance criteria.

Copy only the desired skills into the agent project’s skill directory. For Claude Code running from the Unity project, for example:

```bash
cp -r skills/visora-animation-workflow <unity-project>/.claude/skills/
```

Available skills cover asset import, animation review, rig retargeting, camera/action timing, contact IK, gaze/acting, look development, motion polish, sequence authoring, and animation QA. Read each skill’s trigger description before installing it.

## Troubleshooting

### Bridge is unreachable

Check, in order:

1. Unity Editor is open on the intended project.
2. Unity has finished compiling and has no package compile errors.
3. Native Server Monitor or AnkleBreaker shows a running listener.
4. `UNITY_BRIDGE_MODE` matches the installed bridge.
5. Configured ports include the listener port.
6. `UNITY_BRIDGE_URL` does not contain an embedded port; ports are configured separately.
7. Local firewall/container networking allows the connection.

Use `get_bridge_status(scan_all_ports=true)` to see which candidates answer.

### Unity reports compiling, updating, or reloading

Call `get_editor_state(wait=true)`. If a tool returns `retryable=true`, honor `retry_after_seconds` and retry after Unity settles. Do not restart the MCP server for every normal domain reload; the bridge client remembers the last-good port and has a recovery path.

### A mutation timed out

Do not immediately replay it. A read timeout can occur after Unity applied the change but before Python received the response. Inspect the scene, clip, asset, or operation ID first. See [Bridge failure semantics](backend/BRIDGE.md#request-policy).

### Native tool says a capability is unsupported

Update or re-import `com.visora.editor`, wait for compilation, and confirm its package and ping version. A native flavor does not imply that every historical package version advertises every current feature.

### Screenshot is dark or empty

Run `list_scene_cameras` and `diagnose_camera_framing`, then use `inspect_scene_visual` for a neutral diagnostic-lit comparison. A dark game camera is not proof that geometry is missing.

### Imported glTF/GLB is empty

Install a glTF importer in the Unity project, such as `com.unity.cloud.gltfast`, then import again. Vanilla Unity does not import glTF/GLB itself. Always validate with `inspect_imported_asset` and require real geometry.

### Sketchfab search ignores the query

Use `web_search_assets` to find the actual model page and pass its returned `sketchfab:<uid>` as `asset_id`. Configure `SKETCHFAB_API_TOKEN` for download resolution.

### `.env` appears to be ignored

Confirm the MCP process working directory. `backend.config` reads `.env` from the current directory. Repository client configs should use `uv run --directory /absolute/path/to/Visora visora`, or place variables directly in the client configuration. Restart the MCP process after changing settings because configuration and domain bridge clients are cached for the process lifetime.

### MCP client cannot open an artifact

Artifact paths are created relative to the server working directory and returned as absolute paths from that environment. For Docker, mount an artifact volume visible to the host. For a remote MCP process, transfer the artifact or request inline image/video data where supported.

## Next steps

- Use [Agent workflows](AGENT_WORKFLOWS.md) for safe task sequences.
- Read [Concepts](CONCEPTS.md) for the reasoning behind inspect/mutate/verify.
- Read [Backend architecture](backend/README.md) before extending the implementation.
