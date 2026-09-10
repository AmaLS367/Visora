# Documentation visual assets

This directory contains Visora’s documentation illustrations. They were generated with the built-in image generation tool using `banner.png` as a style reference, then exported as high-quality JPEG files for substantially smaller repository size.

## Asset map

| Asset | Concept | Primary use |
| --- | --- | --- |
| `banner.png` | Visora identity | Root README hero |
| `concepts-workflow.jpg` | Inspect → act → verify | README, concepts, agent workflows |
| `system-architecture.jpg` | MCP client → Python → bridge → Unity | Documentation index, setup, backend architecture |
| `bridge-recovery.jpg` | Port discovery and domain-reload recovery | Bridge internals |
| `typed-contracts.jpg` | External payloads normalized into typed results | Tools and schemas |
| `state-safety.jpg` | Preflight, scoped mutation, rollback, verification | State and safety |
| `asset-pipeline.jpg` | Quarantine and verified Unity import | Asset pipeline |
| `development-workflow.jpg` | Python/Unity validation tracks | Development and roadmap |
| `native-unity-runtime.jpg` | Loopback, router, main thread, native services | Unity package README |

## Shared art direction

Use this prefix for future illustrations:

```text
Use the existing Visora banner as a style reference only. Match its near-black technical background,
neon cyan and electric violet palette, crisp white highlights, precise futuristic geometry, and
restrained glow. Use a premium isometric editorial technology style with vector-like edges, subtle
glass and metal depth, generous margins, and a cinematic 16:9 landscape composition suitable for
developer documentation. Do not reproduce the banner lettering.
```

Use this constraint suffix:

```text
No text, letters, numbers, watermark, tiny labels, clutter, or photoreal people. The illustration
must communicate through composition and symbols; explanatory wording belongs in the Markdown
caption and alt text.
```

## Prompt set

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
