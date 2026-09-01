# Changelog

All notable changes to the `com.visora.editor` package will be documented in this file.

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
