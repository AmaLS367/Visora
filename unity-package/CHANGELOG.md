# Changelog

All notable changes to the `com.visora.editor` package will be documented in this file.

## [1.2.0] - 2026-09-03

### Added
- `MainThreadDispatcher.EnqueueSteppedAsync`: runs a routine one step per editor update tick, so
  editor work can span real time instead of being confined to a single main-thread call.
- `/api/visora/animation/preview-sequence`: deterministic Edit Mode preview that samples an
  AnimationClip at exact timestamps, renders one frame per sample, restores the target pose, and
  leaves a previously clean scene clean.
- Sequence responses now report `requestedFps`, `actualFps`, measured per-frame `timestamp` values,
  and a `timingSource` so clients can encode video at the rate actually achieved.

### Fixed
- `/api/visora/camera/sequence` captured every frame inside one main-thread call, so no editor
  update ran between renders and all frames were copies of a single instant. It now records across
  real editor time, and `frameIntervalSeconds` is honoured instead of only being echoed as a
  timestamp label.

### Changed
- Native contract reports version `1.2.0` and `apiVersion` 3, advertising the
  `camera_sequence_realtime` and `animation_preview_sequence` features.
- Sequence capture is bounded to 240 buffered frames, with an explicit warning when clamped.

## [1.0.0] - 2026-09-01

### Added
- Initial release of the native Visora Unity Editor package.
- Built-in lightweight HTTP server running on `HttpListener` with main thread dispatching.
- Native endpoints for Camera rendering and sequence capture (`/api/visora/camera/render`, `/api/visora/camera/sequence`).
- Native Task queue and coroutine runner with ticket lifecycle (`/api/queue/status`, `/api/queue/cancel`).
- Scene transaction and undo group manager (`/api/visora/transaction/begin`, `/commit`, `/rollback`).
- Mesh, skeleton, and AnimationClip diagnostic services.
- Editor monitor window accessible via `Window > Visora > Server Monitor`.
- Compatibility layer for standard AnkleBreaker bridge endpoints.
