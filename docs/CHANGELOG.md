# Changelog

All notable changes to the **Visora** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Native real-time sequence recording:** Unity records a whole camera sequence on its own clock and returns it in one response. Measured against a live editor, `diagnostic_lit` went from 0.58 to 9.65 fps and `game_camera` reached 10.8 fps, because per-frame capture spent a bridge round trip on every frame.
- **`authored_clip` capture mode:** samples an AnimationClip at exact timestamps in Edit Mode, hitting 23.999998 of a requested 24 fps in 1.87s with no domain reload, and restoring the target pose afterwards.
- **Measured frame timing:** sequences report `actual_fps` and `timing_source` (`native_realtime`, `edit_mode_sampled`, or `python_wallclock`), and MP4 is encoded at the rate actually achieved so playback runs at real speed.
- **C# compile gate:** `scripts/check_unity_package.py` builds the Unity package against real Unity assemblies with .NET and Unity analyzers, in CI as well as locally. Unity was previously the only thing that ever compiled this code.

### Fixed

- **`get_video_mp4` rejected its own default frame rate ([#6](https://github.com/AmaLS367/Visora/issues/6)):** it validated fps up to 30, then delegated to `get_video_frames`, which re-validated at the 12 fps frame-payload limit. Both tools now share a capture core with their own ceiling.
- **Transient Unity responses during domain reload:** the bridge answers 200 with an empty or non-JSON body while reloading, which surfaced as a raw `JSONDecodeError` that no retry path recognised. All decode sites now raise a typed `BridgeProtocolError`, and the play-mode and readiness polls treat it as transient.
- **Stale first Game View frame:** `game_camera` discards frames still showing pre-Play-Mode content, warning instead of failing when a scene is simply static.
- **Lost recordings on a single dropped frame:** a transient bridge failure is retried instead of ending the sequence.
- **Duplicated frame warnings:** an identical per-frame caveat is reported once with its frame count, rather than repeated for every frame.
- **Unity 6 deprecations:** replaced `FindObjectsOfType`, `AssetDatabase.ImportPackage`, and `EntityId.GetRawData` with their current equivalents.

---

## [0.1.2] - 2026-09-03

### Added

- Apache License 2.0, declared through SPDX metadata and included in both wheel and source distributions.
- Open-source contribution foundation: bug, feature, and usage-question forms; pull-request template; contributor guide; security policy; code of conduct; and support guide.
- Complete PyPI metadata with authorship, discovery keywords, classifiers, and canonical project links.
- PEP 561 `py.typed` marker and PyPI-ready README with an installation and Unity bridge quickstart.
- Distribution integrity gates that run `twine check` and verify the license and typing artifacts before release upload.

---

## [0.1.1] - 2026-09-03

### Added

- **Asset web search and Unity import workflow:** agents can discover 3D assets on the web, download models, environments, rigs, textures, and props, then import them into the active Unity project. Direct `sketchfab:<uid>` resolution is supported when a model is already known.
- **Asset-download security hardening:** HTTPS-only public-host validation, quarantine staging outside the Unity project, download and archive limits, collision-safe naming, and post-import inspection prevent a reported import from masking an empty or invalid result.
- **Production CI/CD:** GitHub Actions now validates formatting, linting, strict typing, unit/integration coverage, and the Unity package; matching version tags build distributions and publish the PyPI package and GitHub release.
- **Polished Docker support:** hardened multi-stage image with a locked, bytecode-compiled, non-editable Python environment and a dedicated non-root runtime user.
- **Secure Compose runtime:** stdio-ready MCP configuration with a read-only root filesystem, dropped Linux capabilities, no-new-privileges policy, isolated writable asset cache, and configurable host Unity bridge connectivity.
- **Container regression gate:** CI builds the production image and runs it under the same hardened runtime restrictions.
- **Reproducible base images:** Docker base-image tags are pinned to immutable digests and kept current through Dependabot pull requests.

See the [v0.1.1 roadmap](ROADMAP.md#-released-in-v011) for the delivery status and scope of these milestones.

---

## [0.1.0] - 2026-09-02

### 🚀 Initial Release

The initial production release of **Visora**, a high-level Model Context Protocol (MCP) server for Unity Editor enabling AI agents to inspect, diagnose, and manipulate Unity scenes with visual understanding, rig intelligence, and scene safety guarantees.

### Added

#### 👁️ Vision & Visual Diagnostics
- `take_screenshot`: Capture high-resolution viewport or game screenshots with base64 and artifact storage support.
- `render_camera`: Render custom camera viewpoints with depth buffer analysis, clipping plane validation, and aspect ratio controls.
- `project_viewport_point`: Project 3D world space coordinates to 2D normalized viewport space with on-screen bounding and visibility flags.
- `record_viewport_video`: Capture animated sequence videos (WebP/MP4) from Unity cameras for temporal motion validation.

#### 🎞️ Animation & Rigs
- `inspect_animation_clip`: Parse `AnimationClip` curves, keyframes, and property bindings with automatic translation/scale drift detection.
- `sample_animation_pose`: Sample transform states across skeletons at arbitrary timestamps with pose difference calculations.
- `inspect_skeleton`: Inspect imported hierarchy nodes with exact and fuzzy bone name matching, detecting duplicate or auxiliary helper bones.
- Advanced bone chain parsing supporting complex humanoid and MMD rigs (primary and D-bone structures).

#### 🧶 Skinned Mesh Diagnostics
- `inspect_skinned_mesh`: Comprehensive mesh deformation inspection, checking bounding box validity, bone weights, root bone integrity, and submesh/material alignment.
- Distinction between rendering/texture artifacts and underlying rigging/geometry defects.

#### 🛡️ Scene Safety & Operations
- `safe_scene_transaction`: Transactional wrapper for editor operations with automatic snapshotting and rollback on error.
- Play Mode vs Edit Mode lifecycle safety checks preventing unintended asset corruption during runtime.
- Unity compilation state detection and idle state awaiting.

#### 🔌 Bridge Transport & Native Integration
- Resilient multi-port HTTP bridge client (`8080`–`8085`) supporting AnkleBreaker bridge endpoints.
- Full parity with bundled native `com.visora.editor` Unity package.
- Async ticket/queue polling with backoff for long-running editor coroutines.
- FastMCP server entrypoint with CLI support (`visora` / `python -m backend.server`).
- Strongly typed Pydantic v2 schemas for all 24 MCP tools.

#### 📚 Documentation & Tooling
- `docs/AGENT_WORKFLOWS.md`: Step-by-step diagnostic recipes, camera projections, rig/animation debugging, and agent safety rules.
- `docs/SETUP_GUIDE.md`: Integration guide for Claude Desktop, Cursor, Antigravity, and OpenCode.
- `docs/ROADMAP.md`: Project roadmap and feature delivery tracker.
- Comprehensive test suite covering config, bridge failover, schemas, and native execution parity.
