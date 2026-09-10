# 📦 Visora Editor Bridge Changelog

All notable changes to the `com.visora.editor` Unity package are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## 🚀 [1.2.0] — 2026-09-03

### ✨ Added
- **Stepped Coroutine Runner:** Added `MainThreadDispatcher.EnqueueSteppedAsync` to execute routines across real editor update ticks instead of freezing in a single frame.
- **Deterministic Animation Previews:** Introduced `/api/visora/animation/preview-sequence` for deterministic Edit Mode pose sampling across exact timestamps, rendering one frame per sample and restoring the initial scene pose upon completion.
- **Dynamic Timing Diagnostics:** Sequence responses now include `requestedFps`, `actualFps`, measured per-frame `timestamp` arrays, and `timingSource` metadata for accurate downstream video encoding.
- **Optimized Diagnostic Lighting:** Added native `/api/visora/camera/diagnostic` and `/api/visora/camera/diagnostic-sequence` endpoints. Diagnostic cameras and lights are constructed once per sequence rather than recompiled per frame.

### 🐛 Fixed
- **Multi-Frame Real-Time Sequence Capture:** Fixed an issue where `/api/visora/camera/sequence` captured all frames within a single main-thread update, causing duplicate frames. It now steps across real Editor time, honoring `frameIntervalSeconds`.

### 🔄 Changed
- **API Contract v3:** Advanced package contract to version `1.2.0` (`apiVersion: 3`), advertising `camera_sequence_realtime` and `animation_preview_sequence` capability flags.
- **Buffer Safety Bounds:** Bounded sequence capture to a maximum of 240 buffered frames, returning explicit warnings if clamped.

---

## 🌟 [1.0.0] — 2026-09-01

### ✨ Added
- **Native Editor Bridge Core:** Initial release of the native Visora Unity Editor package (`com.visora.editor`).
- **Loopback HTTP Server:** Embedded lightweight HTTP server built on `System.Net.HttpListener` with automatic assembly reload handling.
- **Main Thread Dispatcher:** Serialized execution queue moving HTTP worker tasks safely onto `EditorApplication.update`.
- **Native Camera Endpoints:** Added `/api/visora/camera/render` and `/api/visora/camera/sequence` with PNG and JPEG encoding.
- **Asynchronous Task Queue:** Added `/api/queue/status` and `/api/queue/cancel` with ticket-based lifecycle tracking.
- **Undo Transaction Manager:** Added atomic transaction lifecycle endpoints (`/api/visora/transaction/begin`, `/commit`, `/rollback`).
- **Diagnostic Services:** Integrated native mesh bounds, skeleton hierarchy, and AnimationClip curve analysis.
- **Editor GUI Monitor:** Added Server Monitor window accessible via **Window > Visora > Server Monitor** for runtime management and port configuration.
- **AnkleBreaker Bridge Compatibility:** Full backwards-compatible support for legacy AnkleBreaker bridge endpoints.
