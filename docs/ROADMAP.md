# Visora — Roadmap

Legend: ✅ done · pending

* * *

## Feature Status

| # | Feature | Scope | Status |
|---|---------|-------|--------|
| 1 | Visual scene understanding | Agent can look at the Unity scene through camera screenshots, compare what changed, and understand visual problems instead of relying only on logs. | ✅ |
| 2 | Camera-aware verification | Agent can render from any Unity camera, project world points/transforms into viewport space, detect off-screen objects, depth issues, clipping, and bad framing. | ✅ |
| 3 | Safe Unity scene operations | Agent can execute editor operations without corrupting the scene: handle Play Mode/Edit Mode, wait for Unity idle state, save only when safe, and restore temporary changes. | ✅ |
| 4 | Animation inspection and sampling | Agent can inspect AnimationClips, see all bindings and curves, detect dangerous position/scale curves, sample animation at a specific time, and verify the sampled result. | ✅ |
| 5 | Skeleton and rig intelligence | Agent can inspect real imported skeletons, find bones by exact and fuzzy names, detect duplicate/helper bones, and understand complex rigs like MMD primary/D-bone chains. | ✅ |
| 6 | Skinned mesh diagnostics | Agent can diagnose mesh deformation, abnormal bounds, broken bone bindings, material/submesh mismatch, and distinguish geometry/skinning bugs from texture/material bugs. | |
| 7 | Reliable Unity bridge layer | Agent gets a stable high-level MCP interface over Unity bridge transport: port discovery, queue/ticket handling, structured errors, timeouts, and clear bridge availability state. | |
| 8 | Structured tool outputs | Every Visora tool returns typed, compact, agent-friendly data instead of raw Unity logs or fake success responses. | |
| 9 | Agent workflow documentation | Clear setup docs for using Visora with agents, Unity projects, AnkleBreaker bridge, environment config, and practical debugging workflows. | |
| 10 | Production test coverage | Tests cover config, bridge behavior, queue polling, scene transactions, tool schemas, and mocked Unity responses so regressions are caught before real Unity sessions. | |
| 11 | Dedicated Visora Unity package | If the AnkleBreaker bridge becomes a limitation, Visora gets its own Unity package for camera rendering, editor coroutines, persistent diagnostics, and stable custom endpoints. | |

* * *

Progress: 5 / 11 done
