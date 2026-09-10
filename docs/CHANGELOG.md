# Changelog

All notable changes to the **Visora** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

> Work in progress toward v0.1.4 (Prefab-First Production Workflow). Only roadmap items 1 and 2
> below have landed; the remaining items (selective apply, prefab authoring, Prefab Stage, mutation
> safety) are not implemented.

### Added

- **Prefab Asset and Variant Inspection (roadmap v0.1.4 item 1):** new read-only MCP tool
  `inspect_prefab_asset(asset_path)` that inspects a Prefab asset directly on disk.
  - Reports the normalized project-relative path, Prefab name and GUID, Prefab kind
    (`regular` / `variant` / `model`), the base Prefab of a Variant, the root GameObject, a
    depth-first hierarchy with stable prefab-relative paths, per-object components (including
    unresolved MonoBehaviour scripts) and `activeSelf`, every nested Prefab instance with its source
    asset path, GUID and connection status, the unique sorted set of Prefab assets a future edit
    could target, full object/component totals, and a `truncated` flag with warnings.
  - **Never instantiates anything in the active scene.** Unity loads the Prefab through
    `PrefabUtility.LoadPrefabContents` and always unloads it in a `finally` block, so the active
    scene, its dirty state, the selection, and any open Prefab Stage are untouched. No scene Undo
    transaction is opened - the operation is strictly read-only.
  - Distinguishes missing assets, non-Prefab assets, broken Prefab sources, a Play Mode / busy
    Editor, and bridge failures as separate explicit errors; a partially failed inspection never
    returns `success=true`.
  - New domain package `backend/tools/prefab/`, typed models in `backend/schemas/prefab.py`,
    canonical bridge method `UnityBridge.inspect_prefab_asset_native`, native Unity service
    `PrefabInspectionService.cs`, endpoint `POST /api/visora/prefab/inspect`, and the
    `prefab_asset_inspection` capability flag. An AnkleBreaker bridge receives an explicit
    unsupported-capability error rather than an improvised C# emulation.
  - Result size is bounded by `PREFAB_MAX_HIERARCHY_NODES` (default 200), enforced by Unity and
    re-checked by the Python layer.
- **Typed Prefab Override Inspection (roadmap v0.1.4 item 2):** new read-only MCP tool
  `inspect_prefab_overrides(instance_path, include_default_overrides=False, scope="nearest",
  max_overrides=200, scene_path=None)` that diffs a Prefab instance in any loaded scene against its
  source Prefab asset.
  - Reports the resolved instance root (nearest or outermost), source asset path and GUID, Prefab
    kind, connection status, totals and per-category counts, `truncated`, and typed overrides:
    modified properties (source and instance values, structured object references with asset path,
    GUID and local file ID), added and removed components (with type and same-type ordinal), and
    added and removed child GameObjects.
  - Each override has a deterministic `override_id` (SHA-256 of its canonical semantic identity,
    never an InstanceID or traversal index), the editable target assets in source-chain order, a
    recommended target, and `applicable` / `not_applicable_reason`. Default overrides are detected
    by Unity, excluded by default, and never applicable; Model Prefab and immutable sources are
    reported as non-applicable. ID collisions are flagged and reported, not merged.
  - Strict hierarchy resolution across all loaded scenes: indexed `Name[k]` segments for same-name
    siblings, explicit missing/ambiguous path errors with candidates, optional `scene_path`.
  - Strictly read-only: nothing is applied, reverted, saved, selected, or dirtied, and no Undo is
    recorded. Requires Edit Mode. An incomplete or inconsistent Unity payload is `success=false`.
  - Canonical bridge method `UnityBridge.inspect_prefab_overrides_native`, native service
    `PrefabOverrideInspectionService.cs`, endpoint `POST /api/visora/prefab/overrides`, and the
    `prefab_override_inspection` capability flag. AnkleBreaker bridges receive an explicit
    unsupported-capability error.

### Changed

- **Shared payload normalization:** `warns` and `coerce_literal` moved from
  `backend/tools/animation/common.py` to `backend/tools/payload.py` so non-animation domains can
  reuse them. All callers were updated to the new canonical import; no compatibility alias remains.
- **Shared prefab plumbing:** `safe_int` moved from `backend/tools/prefab/inspection.py` to
  `backend/tools/payload.py`; the capability → editor-idle → Edit Mode preflight, asset-path cleanup,
  and hierarchy-path normalization live in `backend/tools/prefab/common.py` and are used by both
  prefab tools. On the Unity side, `HierarchyPaths.cs` now owns the `Name[k]` sibling-segment
  convention for both prefab services.

---

## [0.1.3] - 2026-09-10

### Added

- **10 Agent Skills for Production Animation, IK, & Action Workflows:** reusable, prescriptive skills under `skills/` establishing deterministic verification routines, tool sequences, and safety constraints:
  - `visora-animation-workflow`: guides character rig/Avatar preflight, safe low-resolution Edit Mode preview iterations, contact constraint analysis, keyframe hold authoring, and final capture criteria without risking scene corruption or inferring success from static screenshots.
  - `visora-camera-action-workflow`: enforces a single authoritative impact timestamp $T_{\text{impact}}$ orchestrating character holds, camera recoil, flash triggers, and hit-stops without unsynchronized procedural screen shake.
  - `visora-rig-retarget-workflow`: guides imported rig inspection, Humanoid preflight, Avatar blocker diagnosis, mocap retargeting verification, contact IK baking, and explicit fallback paths for Generic/non-Humanoid rigs.
  - `visora-contact-ik-workflow`: prescribes contact phase identification, limb chain verification, pole vector selection, reachability analysis, and continuous curve baking to lock effectors and eliminate foot/hand sliding.
  - `visora-gaze-and-acting-workflow`: prescribes hierarchical look-at gaze distribution across chest, neck, head, and eyes, anatomical limit verification, and natural posture evaluation.
  - `visora-animation-qa-workflow`: prescribes automated mathematical QA passes covering curve discontinuity scans, angular velocity/jerk spikes, foot sliding verification, and regression metrics.
  - `visora-motion-polish-workflow`: prescribes applying the 12 principles of animation in 3D, kinematic joint jerk smoothing, and spacing verification.
  - `visora-camera-contact-workflow`: prescribes authoring high-impact character-camera interactions (drops, stomps, lens strikes), viewport effector alignment, synchronized hit-stops, and recoil impulses.
  - `visora-lookdev-workflow`: prescribes verifying scene lighting contrast, material albedo ranges, exposure balance, and silhouette readability.
  - `visora-sequence-authoring-workflow`: prescribes coordinating multi-track scenes, simultaneous character animations, camera trajectories, and keyframe events using atomic transactions.
  - Skill integrity test suite: `tests/unit/skills/test_skills.py` systematically validating YAML frontmatter, naming conventions, required sections, tool references, and safety rules across all skills.
- **Inverse Kinematics, Viewport Effector Alignment, & Character Gaze:** typed MCP tools and native endpoints for character posing and kinematic problem-solving:
  - `solve_two_bone_ik`: analytical 3D Two-Bone inverse kinematics solver for arm and leg chains with target position, pole vector orientation, optional angle limits, and curve baking to AnimationClip (`backend/tools/animation/ik.py`).
  - `place_effector_in_viewport`: computes 3D world targets from normalized 2D camera viewport coordinates `(x, y, depth)` and executes Two-Bone IK to align effectors (hands/feet) directly to camera framing.
  - `solve_character_gaze`: distributes eye-line and head look-at direction naturally across chest, neck, head, and eyes with biomechanical weighting, anatomical rotation limits, and optional curve baking (`backend/tools/animation/gaze.py`).
  - Native Unity bridge endpoints: `/api/visora/animation/ik/two-bone`, `/api/visora/animation/ik/viewport-align`, and `/api/visora/animation/gaze/solve` via `InverseKinematicsService.cs` and `GazeService.cs`.
- **Temporal Motion QA, Curve Discontinuity Diagnostics, & Motion Polish:** mathematical animation diagnostics and smoothing tools:
  - `detect_curve_discontinuities`: mathematical scan for first- and second-derivative velocity/acceleration jumps, tangent mismatches, and Euler flip discontinuities ($>180^\circ$) across AnimationClip curve bindings (`backend/tools/animation/qa.py`).
  - `analyze_joint_motion`: temporal QA scanner evaluating angular velocity, acceleration jerk, and foot sliding thresholds across animation timelines.
  - Kinematic smoothing via native `AnimationMotionQAService.cs`: reduces excessive joint jerk and trajectory jitter while preserving key silhouette poses.
  - Vocabulary coercion and error resilience (`backend.tools.animation.common`): added `warns()` and `coerce_literal()` helpers to safely handle unknown or unmodelled Unity bridge enum responses in `MotionAnomaly`, `CurveDiscontinuityItem`, and `BodyPenetrationEvent`.
- **Camera-Subject Action Coordination, Effector Contact Baking, & Atomic Transactions:**
  - `author_camera_subject_action`: coordinates high-impact beats (drops, stomps, lens strikes) aligning character effectors to the camera viewport, authoring synchronized hit-stops, camera recoil impulses, and lens flashes at exact impact timestamps ($T_{\text{impact}}$).
  - `bake_effector_contact`: stepped Edit Mode contact locking for limbs/effectors against ground or geometry over designated contact time ranges to eliminate foot sliding.
  - `analyze_self_intersections`: detects mesh and bone self-penetration and volume collision anomalies across animated poses, supporting generic skeleton segment detection and outlier filtering (`AnimationSelfIntersectionService.cs`).
  - `edit_animation_transaction`: atomic multi-operation transaction runner for AnimationClips (upserting keys, removing keys, adding/removing animation events, hold ranges) with automatic pre-mutation backup snapshots under `VisoraBackups/`, unified Undo grouping, and automatic rollback on error (`AnimationTransactionService.cs`, `AnimationRollbackService.cs`).
  - Non-destructive C# authoring helpers: `AnimationSampling` for safe `AnimationMode` lifecycle and `AnimationCurveWriter` for tangent-preserving, non-destructive curve writes.
- **Humanoid Retargeting and Contact Constraints MCP Tools:** 5 typed MCP tools for character setup, retargeting validation, and contact dynamics:
  - `validate_humanoid_avatar` for diagnosing avatar validity, required bone hierarchy (15 required bones), T-pose/A-pose orientation, and scale anomalies with actionable `AvatarBlocker` diagnostics.
  - `configure_humanoid_avatar` for configuring imported character models via `ModelImporter` (`create_new` or `copy_from_other`).
  - `preview_humanoid_retarget` for testing animation compatibility on humanoid rigs, detecting unmapped bones, root motion drift, and posture distortions.
  - `analyze_contact_constraints` for stepped Edit Mode contact analysis, detecting foot sliding, ground penetration, and effector phase transitions.
  - `bake_contact_constraints` for 3D Two-Bone analytical IK baking to lock contacts and eliminate foot slipping, with automatic `.anim` cloning for read-only FBX assets, pre-mutation snapshots under `VisoraBackups/`, and Undo support.
  - Native package capabilities: `/api/visora/humanoid/*` endpoints with `humanoid_avatar_diagnostics`, `humanoid_avatar_configuration`, and `humanoid_contact_constraints` feature detection.
- **AnimationClip Keyframe, Event, and Backup Management:**
  - `list_animation_keyframes` for multi-channel curve inspection, tangent modes, and step-tangent hold ranges.
  - `list_animation_backups` and `restore_animation_clip` for automatic pre-mutation asset snapshots stored under `VisoraBackups/` and atomic file rollback.
  - Native package capability: typed native HTTP endpoints under `/api/visora/animation/*` with feature detection (`animation_authoring`), idempotency tracking, undo registration, and atomic backup snapshots.
- **Reproducible Preview Artifacts & Comparison Engine:** stable artifact records and regression diffing for animation iteration:
  - `AnimationPreviewRecord` schema and atomic storage engine in `backend.tools.animation.preview_store`, organizing preview runs under `artifacts/animation_previews/<preview_id>/` with `record.json`, MP4 video, and extracted keyframe PNGs.
  - New MCP tools: `get_animation_preview_record` for loading full preview manifests and `list_animation_preview_records` for compact historical summaries.
  - Upgraded `compare_animation_previews` with `preview_compare` engine: diffs preview inputs, motion metrics, peak timestamps, and generates side-by-side visual contact sheet artifacts comparing before/after keyframes.
- **One-Step Animation Review & High-FPS Preview:**
  - `preview_animation` one-step review: one Edit Mode call inspects an authored clip, preserves its full range within the native frame ceiling, captures a low-resolution MP4, selects timestamped boundary/event/motion key frames, and returns motion and restoration diagnostics. Live verification on `Тестинг` captured `RebeccaDropkick` at an actual 24.0 fps across 49 frames; auto-framing corrected a clipped `Main Camera` view with a temporary camera that was destroyed afterwards, while the target pose and clean scene state were restored.
  - `authored_clip` capture mode: samples an AnimationClip at exact timestamps in Edit Mode, hitting 23.999998 of a requested 24 fps in 1.87s with no domain reload, and restoring the target pose afterwards.
  - Native real-time sequence recording: Unity records a whole camera sequence on its own clock and returns it in one response (`diagnostic_lit` went from 0.58 to 9.65 fps and `game_camera` reached 10.8 fps).
  - Measured frame timing: sequences report `actual_fps` and `timing_source` (`native_realtime`, `edit_mode_sampled`, or `python_wallclock`), and MP4 is encoded at the rate actually achieved so playback runs at real speed.
- **Real Unity End-to-End Animation Fixtures & C# Test Suites:** deterministic integration fixtures and end-to-end test suites for the production workflows that mocks cannot establish:
  - C# EditMode integration test suites (`unity-package/Tests/Editor/`):
    - `HumanoidRigIntegrationTests`: validates Generic rig `AvatarBlocker` diagnostics, actionable suggestions, and missing bone warnings; validates complete 15-bone Humanoid rig in canonical T-pose with zero blockers and angular symmetry; verifies four-limb contact constraint analysis via `HumanoidContactService.AnalyzeContacts`.
    - `AnimationPreviewIntegrationTests`: validates high-FPS (24 fps and 30 fps) Edit Mode preview routine timing, exact frame counts, non-empty frame textures, auto-framing camera creation/destruction lifecycle without GameObject leaks, and full character transform restoration (`poseRestored == true`).
    - `FastImpactHitStopIntegrationTests`: validates multi-clip camera-subject contact and hit-stop synchronization at exact impact timestamps ($T_{\text{impact}}$), verifying recoil trajectory curves on camera, hold ranges on character limbs, and clean resting scene state.
  - Headless Unity batchmode EditMode test runner: `scripts/check_unity_tests.py` runs tests inside Unity Editor (`6000.6.0f1`) in batchmode with NUnit XML output (37/37 passing).
  - Deterministic Python E2E fixtures (`tests/integration/test_animation_e2e_fixtures.py`):
    - Multi-phase domain reload recovery: verifies client resilience across socket connection drops, transient empty HTTP 200 responses, and non-JSON HTML bodies until bridge re-binding is complete.
    - Stale first Game View frame detection: validates `_discard_stale_frames` comparing against baseline, discarding pre-Play-Mode content, and awaiting dynamic frames.
    - Physical artifact verification: inspects real files on disk, ensuring `record.json` matches `AnimationPreviewRecord` schema, MP4 files have valid `ftyp` container headers, and keyframes are valid PNGs.
  - C# compile gate: `scripts/check_unity_package.py` builds the Unity package against real Unity assemblies with .NET and Unity analyzers, in CI as well as locally.

### Changed

- **MCP Token Overhead Reduction & Agent Context Protection:**
  - **82% reduction in MCP tool definition tokens:** implemented custom `VisoraMCPServer` overriding `list_tools` to strip redundant `output_schema` definitions, stripped duplicated Args/Returns docstring sections while preserving operational guidance, and stripped cosmetic `title` properties from parameter JSON schemas (`COMPACT_TOOL_DEFINITIONS`).
  - **Compacted tool execution results:** added `compact_tool_results` setting (enabled by default) to override `call_tool` in `VisoraMCPServer`, stripping duplicate `structured_content`, and stripping `None`/null fields and indentation whitespace from TextContent JSON payloads, significantly reducing agent context consumption per tool call.
  - **Throttled diagnostic data dumps & context protection:** added centralized diagnostic dump limits to Settings (`path_filter`, `max_bindings`, `max_transforms` with anomalous bone prioritization, `max_bones`, `max_bone_bindings`, `max_hierarchy_nodes`) and lowered default thresholds by ~50% (`diagnostic_max_bindings`: 25 → 12, `diagnostic_max_transforms`: 25 → 12, `diagnostic_max_bones`: 30 → 16, `diagnostic_max_bone_bindings`: 30 → 16, and `diagnostic_max_hierarchy_nodes`: 50 → 24) to protect LLM context windows while preserving rig/clip topology.
  - **Downscaled inline MCP images & lowered screenshot defaults:** downscaled inline MCP `Image` payloads to at most 1280px on the longest edge via Lanczos resampling (`VISION_INLINE_MAX_DIMENSION`), saving ~55% pixels and context tokens per call while keeping full-resolution PNG artifacts intact on disk across `take_screenshot`, `compare_screenshots`, `inspect_scene_visual`, `preview_animation`, and `capture_video`. Lowered default `take_screenshot` resolution from 1920×1080 to 1280×720.
  - **Multimodal FastMCP vision migration:** replaced base64 string fields with `file_path`, `contact_sheet_path`, and `diff_image_path`, returning native FastMCP `Image` blocks alongside compact metadata schemas and persisting rendered frames, screenshots, and labeled contact sheets under `artifacts/`.
- **MCP Tool Catalog Pruning & Consolidation:**
  - Pruned 11 redundant tools and aliases, reducing the active catalog from 55 tools (46,460 characters) to 44 tools (34,518 characters, -25.7% total footprint):
    - Removed pure aliases `clip_inspector` and `analyze_animation_curves` in favor of canonical `inspect_animation_clip`.
    - Removed single-op keyframe and event authoring tools (`set_animation_keyframe`, `move_animation_keyframe`, `remove_animation_keyframe`, `set_keyframe_hold`, `create_animation_event`, `remove_animation_event`) in favor of atomic `edit_animation_transaction`.
    - Merged polling wrapper `wait_for_editor_idle` into `get_editor_state(wait=True)`.
    - Merged polling wrapper `wait_for_ticket` into `check_ticket_status(wait=True)`.
    - Merged `get_video_frames` and `get_video_mp4` into a unified `capture_video` tool with format selection (`output: Literal["frames", "mp4"]`).
- **Unity C# Package Performance & Refactoring:**
  - Optimized reflection caching: cached reflection lookups across Unity Editor services to eliminate repetitive reflection overhead during animation sampling and bone mapping.
  - Bone matching acceleration: replaced switch patterns and sequential string matches with dictionary lookups and fast lookup tables for humanoid and custom rig bones.
  - Robust animation sampling lifecycle: introduced `AnimationSampling` context ensuring `AnimationMode.StartAnimationMode` and `AnimationMode.StopAnimationMode` are cleanly paired even during unhandled exceptions.
- **Modular Test Suite Architecture (`tests/unit/`):** eliminated flat test directory bloat by reorganizing unit tests into domain-scoped subpackages mirroring the backend structure (`animation/`, `asset/`, `bridge/`, `core/`, `mesh/`, `skills/`, `vision/`):
  - Isolated 19 animation, kinematics, and rig test suites under `tests/unit/animation/` (`test_animation`, `test_ik`, `test_gaze`, `test_contact`, `test_qa`, `test_preview`, `test_transaction`, etc.).
  - Grouped server, configuration, schemas, tool catalog, and diagnostic dump tests under `tests/unit/core/`.
  - Enables targeted domain test execution (e.g. `uv run pytest tests/unit/animation/`) while maintaining 100% test pass rate across all 512 tests, and preserving complete git history and blame tracking.
- **Reactive Bridge Reload Recovery & Failover:**
  - A healthy request costs exactly one round trip (no preemptive probe). Once a request fails with a connection drop or a mid-reload body, the bridge polls Unity's editor state — pinging only the last known-good port, one full rescan at most — until it is idle, then retries the request once. If Unity stays busy past `UNITY_BRIDGE_READY_WAIT_SECONDS` (default 8s) it raises `BridgeBusyError` (`reason` = `compiling` / `updating` / `reloading` / `unreachable`) instead of soaking the full per-request timeout and retry budget (minutes for `execute_code`). Tools surface it as `retryable=true` with `unity_state` and `retry_after_seconds` on the result. New settings: `UNITY_BRIDGE_STATE_PROBE_TIMEOUT_SECONDS`, `UNITY_BRIDGE_READY_WAIT_SECONDS`.
  - Read timeouts on non-idempotent bridge calls are no longer retried: a read timeout means the request already reached Unity, so replaying it could apply the edit twice. `execute_code`, asset import/instantiate, all bakes and IK/gaze solves, and transaction execute/commit/rollback now fail fast on a read timeout (`retry_on_timeout=False`); read-only and operation-id-keyed idempotent endpoints still retry. Recovery never re-sends a request that timed out mid-flight. The bridge also prefers the last working port on reconnect.

### Fixed

- **`get_video_mp4` rejected its own default frame rate ([#6](https://github.com/AmaLS367/Visora/issues/6)):** it validated fps up to 30, then delegated to `get_video_frames`, which re-validated at the 12 fps frame-payload limit. Both tools now share a capture core with their own ceiling.
- **Transient Unity responses during domain reload:** the bridge answers 200 with an empty or non-JSON body while reloading, which surfaced as a raw `JSONDecodeError` that no retry path recognised. All decode sites now raise a typed `BridgeProtocolError`, and the play-mode and readiness polls treat it as transient.
- **Stale first Game View frame ([#4](https://github.com/AmaLS367/Visora/issues/4)):** `game_camera` discards frames still showing pre-Play-Mode content, warning instead of failing when a scene is simply static.
- **Compilation and runtime error visibility ([#5](https://github.com/AmaLS367/Visora/issues/5)):** surfaced compilation errors and runtime diagnostics cleanly in `safe_scene_transaction`.
- **Lost recordings on a single dropped frame:** a transient bridge failure is retried instead of ending the sequence.
- **Duplicated frame warnings:** an identical per-frame caveat is reported once with its frame count, rather than repeated for every frame.
- **Unity 6 deprecations:** replaced `FindObjectsOfType`, `AssetDatabase.ImportPackage`, and `EntityId.GetRawData` with their current equivalents.
- **Docstring indentation in server:** normalized docstring indentation in `compact_tool_description` to prevent malformed MCP tool descriptions.

See the [v0.1.3 roadmap](ROADMAP.md#--planned-for-v013--animation-authoring--temporal-verification) for the delivery status and scope of these milestones.

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
