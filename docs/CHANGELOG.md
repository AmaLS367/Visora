# Changelog

All notable changes to the **Visora** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
