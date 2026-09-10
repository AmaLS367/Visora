# 🎨 Documentation Visual Assets & Design System

> Visual catalog, art direction guidelines, and generative prompts for Visora's editorial documentation graphics.

This directory contains Visora's technical illustrations, designed to visually reinforce key architecture and workflow principles across the documentation.

---

## 🗺️ Asset Gallery & Inventory

| File | Theme & Metaphor | Primary Placement |
| :--- | :--- | :--- |
| `banner.png` | 👁️ **Visora Brand Identity** | Root [README.md](../../README.md) hero header |
| `concepts-workflow.jpg` | 🔄 **Inspect ➔ Act ➔ Verify Loop** | [Concepts](../../docs/CONCEPTS.md) & [Agent Workflows](../../docs/AGENT_WORKFLOWS.md) |
| `system-architecture.jpg` | 🏗️ **End-to-End System Layers** | [Documentation Index](../../docs/README.md) & [Backend Architecture](../backend/README.md) |
| `bridge-recovery.jpg` | 🌐 **Port Discovery & Domain Reload** | [Bridge & Failure Semantics](../backend/BRIDGE.md) |
| `typed-contracts.jpg` | 📐 **Typed Normalization & Compaction** | [Tools & Schemas](../backend/TOOLS_AND_SCHEMAS.md) |
| `state-safety.jpg` | 🛡️ **Transactional Safety & Rollbacks** | [State & Safety](../backend/STATE_AND_SAFETY.md) |
| `asset-pipeline.jpg` | 📦 **Quarantine Staging & Import** | [Asset Pipeline](../backend/ASSET_PIPELINE.md) |
| `development-workflow.jpg` | 💻 **Python & C# Validation Tracks** | [Development Guide](../backend/DEVELOPMENT.md) & [Roadmap](../ROADMAP.md) |
| `native-unity-runtime.jpg` | ⚡ **Unity Main-Thread Services** | [Unity Package README](../../unity-package/README.md) |

---

## 🎯 Shared Art Direction

> [!NOTE]
> All documentation graphics adhere to a cohesive visual language: near-black technical canvas, cyan inspection flows, violet mutation/kinematic solvers, and crisp white verification accents.

Use this prefix for future generative prompts:

```text
Use the existing Visora banner as a style reference only. Match its near-black technical background,
neon cyan and electric violet palette, crisp white highlights, precise futuristic geometry, and
restrained glow. Use a premium isometric editorial technology style with vector-like edges, subtle
glass and metal depth, generous margins, and a cinematic 16:9 landscape composition suitable for
developer documentation. Do not reproduce the banner lettering.
```

Constraint suffix:

```text
No text, letters, numbers, watermark, tiny labels, clutter, or photoreal people. The illustration
must communicate through composition and symbols; explanatory wording belongs in the Markdown
caption and alt text.
```

---

## 📝 Canonical Prompt Set


### Concepts workflow

```text
Illustrate the core Visora idea: an intelligent eye-like observer understanding a live 3D editor
scene, then turning observation into a safe verified action loop. Include a camera frustum,
character rig silhouette, mesh cube, animation timeline, inspection symbol, controlled-action
symbol, and protected verification symbol connected as one calm circular flow.
```

### System architecture

```text
Show a layered architecture from left to right: an AI agent terminal, a precise Python workflow
engine and typed tool network, a resilient bridge with multiple port nodes, and a Unity-like live
3D editor containing a camera, rig, and mesh. Use cyan for command/data flow, violet for results,
and clear visual grouping between the four layers.
```

### Bridge recovery

```text
Visualize a reliable digital bridge reconnecting across a temporary Unity domain reload. Group
several candidate port nodes on one side, place a luminous segmented connection with one section
rebuilding in the center, and a live 3D editor on the other side. Include a state-probe pulse,
last-good route, and calm recovery loop without making the event look catastrophic.
```

### Typed contracts

```text
Show irregular external Unity, HTTP, image, and diagnostic payload fragments entering a faceted
typed-validation prism surrounded by schema blocks. On the other side, emit a small orderly stack
of compact result cards expressing success, warning, retry, and visual evidence only through
simple icons. The visual story is clarity emerging from transport complexity.
```

### State safety

```text
Place a live 3D scene with a character rig, camera, mesh, and animation timeline inside a luminous
protective transaction boundary. Surround it with four connected concepts: preflight, scoped
change, Undo rollback, and visual verification. Show temporary camera/animation state returning
cleanly to its origin; cyan means verified state and violet means recovery.
```

### Asset pipeline

```text
Show an untrusted remote 3D package moving left to right through a quarantine chamber, archive and
path scanner, contained Assets-folder gate, Unity import boundary, and finally a verified textured
3D model in an editor scene. Divert unsafe fragments away from the approved cyan flow using only
clean geometry.
```

### Development workflow

```text
Visualize two balanced development tracks: Python MCP modules and C-sharp Unity modules. Each track
passes through typed schemas, tests, and its own validation checkpoint; both converge through a
compiler/Unity verification chamber into a clean release artifact. Include documentation and a
linked knowledge graph as supporting elements.
```

### Native Unity runtime

```text
Inside a transparent Unity-like application frame, show a loopback network ring entering a router
hub, an orderly serialized main-thread queue, and camera, animation, mesh, asset, and transaction
service modules surrounding one live 3D scene. Emphasize a single controlled main-thread lane and
local-only circulation.
```

## Export

Generated PNG sources were preserved in the image-generation workspace. Project copies were converted to high-quality JPEG to reduce the total illustration footprint from roughly 13 MB to under 3 MB:

```bash
ffmpeg -i input.png -q:v 2 output.jpg
```

Keep `banner.png` as PNG because it contains transparency. Do not overwrite an existing illustration when exploring a new direction; add a versioned candidate and replace references only after review.
