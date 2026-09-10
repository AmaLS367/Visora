# Visora — Roadmap

> **Current Release:** 🚀 **v0.1.3 (Completed)**

<p align="center">
  <img src="assets/development-workflow.jpg" alt="Python and Unity development tracks pass through validation and converge into a verified Visora release" width="100%">
</p>
<p align="center"><em>Each release joins the typed Python workflow layer, native Unity services, tests, and documentation.</em></p>

---

## 🚀 Planned for v0.1.4 — Prefab-First Production Workflow

### 1. 📦 Prefab Asset and Variant Inspection
* **Status:** 🟢 Implemented (unreleased)
* **Scope:** Add typed prefab inspection that identifies the source asset, prefab kind (regular, variant, model, or nested), hierarchy, components, nesting relationships, connection status, and candidate target assets for future edits. Keep results compact and asset-focused so agents can reason about reusable project content without first instantiating it into the active scene.
* **Delivered:** `inspect_prefab_asset(asset_path)` (`backend/tools/prefab/`, `backend/schemas/prefab.py`) reads a Prefab through Unity's isolated prefab-content lifecycle — `PrefabUtility.LoadPrefabContents` with a `finally`-guaranteed unload — so nothing is instantiated in the active scene, no Prefab Stage is opened, and scene dirty state and selection are untouched. Returns Prefab kind, Variant base path, depth-first hierarchy with stable relative paths, per-object components and activity, nested instances with source paths/GUIDs/connection status, the unique sorted edit-target set, real object/component totals, and bounded `truncated` results. Native-only via `POST /api/visora/prefab/inspect` behind the `prefab_asset_inspection` capability; legacy bridges get an explicit unsupported-capability error. Covered by Python unit/contract tests and 10 Unity EditMode fixtures (regular, variant, nested, missing nested source, non-prefab, missing asset, truncation, determinism, exception cleanup, scene preservation).

### 2. 🔎 Typed Prefab Override Inspection
* **Status:** 🟢 Implemented (unreleased)
* **Scope:** Add `inspect_prefab_overrides` for scene instances. Report property overrides, added and removed components, added and removed GameObjects, object references, default overrides, and the prefab asset each change can target. Assign stable override identifiers so an agent can select exact changes instead of relying on an opaque Apply All operation.
* **Delivered:** `inspect_prefab_overrides(instance_path, include_default_overrides=False, scope="nearest", max_overrides=200, scene_path=None)` (`backend/tools/prefab/overrides.py`, `backend/schemas/prefab.py`) resolves any object inside a Prefab instance across all loaded scenes (indexed `Name[k]` segments, explicit missing/ambiguous errors with candidates) and diffs the nearest or outermost instance root against its source asset through Unity's own inspection APIs (`GetObjectOverrides`, `GetPropertyModifications` + `IsDefaultOverride`, `GetAdded/RemovedComponents`, `GetAdded/RemovedGameObjects`). Each override is typed (modified property with source/instance values and structured object references, added/removed component with same-type ordinal, added/removed GameObject), carries a deterministic SHA-256-based `override_id`, source-chain target assets with a recommended target, and `applicable` / `not_applicable_reason` (default overrides, Model Prefabs, immutable sources, ID collisions). Strictly read-only; native-only via `POST /api/visora/prefab/overrides` behind the `prefab_override_inspection` capability, with an explicit unsupported-capability error for legacy bridges. Covered by Python unit/contract tests and 22 Unity EditMode fixtures (regular, nested, Variant, Model, all five categories, default root Transform, object references, same-type components, same-name siblings, missing source, multi-scene and ambiguous paths, state preservation, and repeat-call determinism).

### 3. 🎯 Selective and Explicit Override Application
* **Status:** 🟡 Planned
* **Scope:** Add `apply_prefab_overrides` with selective override IDs, an explicit target asset path, dry-run previews, operation IDs, and source-version checks. Require deliberate opt-in for Apply All, handle nested Prefabs and Prefab Variants without silently choosing the wrong asset, and return a structured summary of applied, skipped, and rejected changes.

### 4. 🧩 Atomic Prefab Asset Authoring
* **Status:** 🟡 Planned
* **Scope:** Provide an asset-scoped prefab transaction that loads a Prefab into an isolated editing context, applies typed mutations, saves it to disk, and always unloads temporary contents. Keep this lifecycle separate from scene Undo transactions because prefab writes are persistent project-wide mutations that can affect every instance of the asset.

### 5. 🏛️ Prefab Stage Lifecycle
* **Status:** 🟡 Planned
* **Scope:** Add `open_prefab_stage` and `save_prefab_stage`, plus prefab-stage state inspection and an explicit close operation with save or discard behavior. Support isolation and in-context modes, return a stage token tied to the opened asset, reject stale or mismatched save requests, and restore the previously active Unity stage after agent work completes.

### 6. 🛡️ Prefab Mutation Safety and Recovery
* **Status:** 🟡 Planned
* **Scope:** Enforce Edit Mode and Unity-idle preflight checks, create a recoverable snapshot before every prefab write, never replay ambiguous mutations after a timeout, and verify the saved asset by reloading and re-inspecting it. Report project-wide impact warnings, preserve scene dirty state where possible, and surface all AssetDatabase, serialization, compilation, and Unity execution failures directly.

### 7. 🧪 Native Bridge Coverage and Production Fixtures
* **Status:** 🟡 Planned
* **Scope:** Add typed Python schemas and tools, dedicated native Unity prefab services and HTTP endpoints, explicit unsupported-capability errors for bridges that cannot provide prefab authoring, and deterministic EditMode integration fixtures for regular Prefabs, nested Prefabs, Prefab Variants, model Prefabs, default overrides, selective apply, rollback, and stage cleanup.

### 8. 🧭 Prefab-First Agent Workflow
* **Status:** 🟡 Planned
* **Scope:** Document and encode the production workflow `inspect → dry-run diff → selective apply or asset edit → save → re-inspect → verify`. Prefer direct prefab asset authoring for reusable content, use Prefab Stage when visual or human-in-the-loop inspection is required, and avoid polluting scenes with temporary editing instances.

---

## 🚀 Released in v0.1.3 — Animation Authoring & Temporal Verification

### 1. 🎥 Reliable High-FPS Animation Preview
* **Status:** ✅ Completed
* **Scope:** Make short `game_camera` previews reliable for animation iteration. Harden Play Mode capture against every transient bridge response observed during domain reloads, including empty/non-JSON successful HTTP responses; wait for bridge re-binding and the first valid Game View render; discard or retry a pre-initialization camera frame; and always restore the original editor mode.
* **Issue #4 follow-up:** The initial domain-reload/reconnect path is released, and explicit `playmode_management` can recover after the reload. Live Unity verification nevertheless exposed an unhandled empty-response edge case in video capture and a stale first Game View frame. Cover both with regressions before considering Play Mode preview dependable.
* **Issue #6:** Make the documented 1–30 fps range of `get_video_mp4` real end-to-end. Its internal capture path must not reapply `get_video_frames`' 12 fps public-payload limit; retain an explicit maximum-frame safety bound and clear validation errors. Keep frame-sequence payload limits intentional and documented separately.
* **Delivered:** Both tools share a capture core with their own fps ceiling, so `get_video_mp4` no longer fails on its own default of 24. Raising the limit alone was not enough: capture spent one bridge round trip per frame, so a 24 fps request really ran at 0.58 fps. Unity now records a sequence on its own clock in a single response (`diagnostic_lit` 0.58 → 9.65 fps, `game_camera` 10.8 fps, both measured live), `authored_clip` samples a clip in Edit Mode at an exact 24 fps, and every sequence reports `actual_fps` and `timing_source` rather than assuming the requested rate. Empty and non-JSON reload responses are typed and retried, dropped frames are retried, stale Game View frames are discarded, and a C# compile gate now builds the Unity package in CI.

### 2. ▶️ One-Step Animation Review
* **Status:** ✅ Completed
* **Scope:** Add a high-level `preview_animation` workflow that prepares the target and clip, captures a low-resolution MP4 from the chosen camera, returns timestamped key frames and motion metrics, and restores temporary animation and editor state. This turns animation review into a fast preview → assess → adjust loop instead of manual per-frame screenshots.
* **Delivered:** Live on scene `Тестинг`, `RebeccaDropkick` captured 49 Edit Mode frames over 2.0 seconds at 24.0 effective and actual fps. The requested `Main Camera` was initially `clipped`, so auto-framing used then destroyed a temporary `Visora Preview Camera`; the pose was restored and the scene remained clean. Key frames covered the jump and landing, and motion was non-static with its peak at 1.083s.

### 3. 🎬 Typed Clip, Event, and Camera Authoring
* **Status:** ✅ Completed
* **Scope:** Provide typed, safe operations to create and edit AnimationClip curves: set or move keys, configure tangents/easing and holds, and create or remove animation events. Support a shared action timeline for character motion, camera recoil, flashes, and hit-stop so every impact has one authoritative timestamp rather than independent procedural effects.
* **Delivered:** Added 9 MCP tools across keyframe manipulation (`list_animation_keyframes`, `set_animation_keyframe`, `move_animation_keyframe`, `remove_animation_keyframe`, `set_keyframe_hold`), event authoring (`create_animation_event`, `remove_animation_event`), and non-destructive backups (`list_animation_backups`, `restore_animation_clip`). Native Unity endpoints via `VisoraHttpRouter` (`animation_authoring` capability) provide typed C# execution, idempotency, and full Undo integration. Automatic pre-mutation snapshots safeguard clip edits under `VisoraBackups/`, with Undo grouping and Edit Mode enforcement.

### 4. 🦿 Humanoid Retargeting and Contact Constraints
* **Status:** ✅ Completed
* **Scope:** Add a workflow to validate/configure imported models as Humanoid, report Avatar creation blockers precisely, and preview compatible mocap retargeting. Add contact-oriented IK/baking primitives for feet and hands, with explicit diagnostics when a rig cannot support the requested constraint.
* **Delivered:** Added 5 MCP tools across humanoid avatar validation (`validate_humanoid_avatar`), ModelImporter configuration (`configure_humanoid_avatar`), mocap retarget preview (`preview_humanoid_retarget`), contact analysis (`analyze_contact_constraints`), and 3D Two-Bone IK baking (`bake_contact_constraints`). Native Unity endpoints via `VisoraHttpRouter` (`humanoid_avatar_diagnostics`, `humanoid_avatar_configuration`, `humanoid_contact_constraints`) provide single-trip execution, precise AvatarBlocker diagnostics, support for standalone and embedded read-only FBX clips, and non-destructive baking with pre-mutation backup in `VisoraBackups/` and full Undo support.

### 5. 🧭 Agent Skills for Animation Workflows
* **Status:** ✅ Completed
* **Scope:** Ship reusable Visora skills that prescribe tool selection and verification order rather than leaving agents to improvise editor scripts:
  * `visora-animation-workflow` — rig/Avatar preflight, low-resolution preview iterations, timing and distance checks, and final-quality capture criteria.
  * `visora-camera-action-workflow` — a single impact timestamp; synchronized pose, camera recoil, flash, and hit-stop; no unsynchronized procedural shake as the default.
  * `visora-rig-retarget-workflow` — imported-rig inspection, Humanoid eligibility, mocap retarget fallback paths, and explicit no-Avatar guidance.
* **Delivered:** Added three first-class skills under `skills/` (`visora-animation-workflow`, `visora-camera-action-workflow`, `visora-rig-retarget-workflow`) with YAML frontmatter and prescriptive step-by-step sequences. Enforced acceptance rules across all skills: direct reporting of concrete bridge/Unity errors, strictly forbidding inferring success from static screenshots, enforcing the smallest safe preview (Edit Mode `preview_animation`) before final capture, anchoring combat beats to a single authoritative impact timestamp $T_{\text{impact}}$ without unsynchronized procedural shake, and providing explicit Generic rig fallback paths when Humanoid Avatar blockers occur. Updated `backend/app.py` instructions and documentation (`SETUP_GUIDE.md`, `AGENT_WORKFLOWS.md`), backed by automated skill integrity tests in `tests/unit/skills/test_skills.py`.

### 6. 🧾 Reproducible Preview Artifacts
* **Status:** ✅ Completed
* **Scope:** Give each animation preview a stable artifact record containing its ID, scene and clip identities, camera, requested and actual capture settings, editor/bridge state, timestamps or named action markers, MP4 path, and generated key frames. Support comparison between two preview records so agents and humans can trace an observed improvement or regression back to the exact inputs.
* **Delivered:** Added `AnimationPreviewRecord` schema and atomic storage engine in `backend.tools.animation.preview_store` organizing each preview run under `artifacts/animation_previews/<preview_id>/` with `record.json`, MP4 video, and keyframes. Integrated stable ID generation and record persistence directly into `preview_animation`. Added `preview_compare` engine and upgraded `compare_animation_previews` to load and diff records across inputs, temporal motion peaks, action markers, and side-by-side visual contact sheets. Added `get_animation_preview_record` and `list_animation_preview_records` MCP tools with comprehensive test coverage.

### 7. 🧪 Real Unity End-to-End Animation Fixtures
* **Status:** ✅ Completed
* **Scope:** Add deterministic Unity integration fixtures and end-to-end tests for the production workflows that mocks cannot establish: Play Mode domain reload and bridge re-binding, empty transient responses, stale first Game View frames, high-FPS MP4 capture, a fast impact/hit-stop sequence, a Generic rig with no Avatar, and a valid Humanoid rig. Assert scene restoration and inspect the produced artifacts, not just API success responses.
* **Delivered:** Added deterministic Unity C# EditMode integration test suites (`HumanoidRigIntegrationTests.cs`, `AnimationPreviewIntegrationTests.cs`, `FastImpactHitStopIntegrationTests.cs`) running in headless batchmode via `check_unity_tests.py` (37/37 passing). Verified Generic rig AvatarBlocker reporting, complete 15-bone Humanoid rig validation with T-pose posture assessment and contact constraint resolution, high-FPS preview routine timing with automatic camera lifecycle/cleanup and transform restoration, and fast camera-subject contact with synchronized impact curves and hit-stop holds. Added Python end-to-end fixtures (`tests/integration/test_animation_e2e_fixtures.py`) testing multi-phase domain reload recovery (connection drops, empty HTTP 200, non-JSON responses), stale first Game View frame detection/discard, disk artifact validation (`record.json`, MP4 container headers, PNG keyframes), and scene restoration.

---

## 🚀 Released in v0.1.2 — Open-Source & Packaging Foundation

### 1. ⚖️ Apache-2.0 Licensing
* **Status:** ✅ Completed
* **Scope:** Added the complete Apache License 2.0 text, SPDX package metadata, and a distributed license file so the reuse and redistribution terms are explicit for all consumers.

### 2. 🤝 Contribution & Community Health
* **Status:** ✅ Completed
* **Scope:** Added structured GitHub issue forms for bugs, feature requests, and questions; a security-aware issue chooser; a PR template; contributor guidance; a security policy; a code of conduct; and support guidance.

### 3. 📦 First-Class PyPI Metadata
* **Status:** ✅ Completed
* **Scope:** Polished `pyproject.toml` with authorship, discovery keywords, Python/platform classifiers, SPDX licensing, and canonical links to source, documentation, issue tracker, and changelog so PyPI presents Visora as a complete package.

### 4. 🧩 Typed & Installable Distribution
* **Status:** ✅ Completed
* **Scope:** Published the PEP 561 `py.typed` marker and improved the PyPI-rendered README with absolute links, an install command, and a concise MCP/Unity bridge quickstart.

### 5. ✅ Distribution Integrity Gates
* **Status:** ✅ Completed
* **Scope:** Extended CI to validate built package metadata and assert that released distributions include legal and typing artifacts before publishing.

---

## 🚀 Released in v0.1.1

### 1. 🌐 Asset Web Search & Auto-Download for Unity
* **Status:** ✅ Completed
* **Scope:** Provide agents with tools to perform web searches and automatically download 3D models, environments, rigs, textures, and props directly into the active Unity project. This empowers AI agents to autonomously discover and import required 3D assets to animate rich, context-complete scenes.
* **Security hardening:** Downloads now use HTTPS-only public-host validation, external quarantine staging, strict format/archive limits, collision-safe names, and verified Unity import results. Sketchfab IDs can be resolved directly by the import tool.

### 2. ⚙️ Production CI/CD (GitHub Actions)
* **Status:** ✅ Completed
* **Scope:** Create a polished, multi-stage GitHub Actions workflow suite covering code formatting (`ruff format`), strict linting (`ruff check`), static typing (`mypy`), automated unit and integration tests (`pytest`), and tag-triggered PyPI/GitHub release publishing.

### 3. 🐳 Polished Docker Support
* **Status:** ✅ Completed
* **Scope:** Delivered a hardened, multi-stage `Dockerfile` and Compose configuration for running Visora as a containerized headless MCP server. The image has a minimal runtime stage, an immutable non-editable Python environment, a dedicated non-root user, bytecode compilation, cache-efficient locked dependency installation, and a restrictive default Compose sandbox with configurable Unity bridge access.

---

## 🚀 Completed Milestones (v0.1.0)

### 1. 👁️ Visual Scene Understanding
* **Status:** ✅ Completed
* **Scope:** Agents can inspect the Unity scene through camera screenshots, compare visual changes, and diagnose rendering or layout problems directly instead of relying solely on logs.

### 2. 📐 Camera-Aware Verification
* **Status:** ✅ Completed
* **Scope:** Agents can render from any scene camera, project 3D world points and transforms into 2D viewport coordinates, and identify off-screen objects, clipping planes, depth errors, or framing issues.

### 3. 🛡️ Safe Unity Scene Operations
* **Status:** ✅ Completed
* **Scope:** Agents can execute editor actions without corrupting the scene: cleanly manage Play Mode / Edit Mode lifecycles, await Unity idle states, enforce safe-save policies, and rollback temporary state.

### 4. 🎞️ Animation Inspection & Sampling
* **Status:** ✅ Completed
* **Scope:** Agents can inspect `AnimationClip` curves and bindings, detect unintended translation/scale drift, sample poses at exact timestamps, and verify keyframe evaluations.

### 5. 🦴 Skeleton & Rig Intelligence
* **Status:** ✅ Completed
* **Scope:** Agents can inspect imported hierarchies, resolve bones via exact and fuzzy matching, identify duplicate or helper bones, and understand complex rigs (such as MMD primary/D-bone chains).

### 6. 🧶 Skinned Mesh Diagnostics
* **Status:** ✅ Completed
* **Scope:** Agents can diagnose mesh deformation anomalies, abnormal bounding boxes, broken bone bindings, and submesh/material mismatches, distinguishing rigging issues from material defects.

### 7. 🔌 Reliable Unity Bridge Layer
* **Status:** ✅ Completed
* **Scope:** Visora provides a resilient high-level MCP bridge layer with automatic multi-port discovery, async ticket/queue polling, structured exception handling, and health probes.

### 8. 📦 Structured Tool Outputs
* **Status:** ✅ Completed
* **Scope:** Every Visora tool returns compact, strongly typed Pydantic models designed for LLM reasoning rather than unstructured console dumps or uninformative success flags.

### 9. 📚 Agent Workflow Documentation
* **Status:** ✅ Completed
* **Scope:** Comprehensive guides covering setup instructions, agent diagnostic recipes, client configurations (Claude Desktop, Cursor, Antigravity, OpenCode), and safety protocols.

### 10. 🧪 Production Test Coverage
* **Status:** ✅ Completed
* **Scope:** Full test suite covering configuration, bridge transport, queue polling, scene transactions, tool output schemas, and mocked Unity responses to prevent regressions.

### 11. 📦 Dedicated Visora Unity Package
* **Status:** ✅ Completed
* **Scope:** Native Unity companion package alongside AnkleBreaker support for custom camera rendering, editor coroutines, persistent diagnostics, and stable custom endpoints.
