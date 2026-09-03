---
name: visora-asset-workflow
description: Use before calling Visora's search_assets, web_search_assets, or download_and_import_asset MCP tools to find and import 3D assets into a Unity project. Covers Sketchfab's broken search, which file formats Unity can actually import, and how to verify an import really worked instead of trusting a bare success=true.
---

## Visora asset workflow

Visora exposes MCP tools for finding, downloading, and importing 3D assets (models, textures,
materials) into a Unity project: `search_assets`, `web_search_assets`, `download_and_import_asset`,
`inspect_imported_asset`, `instantiate_scene_asset`. Every gotcha below was hit live, once, against
the real providers/Unity - not theoretical.

### Searching

- **ambientCG** (`source="ambientcg"`): free, no key, real search. Use `category` to filter
  (`model`, `texture`/`material`, `hdri`).
- **Sketchfab** (`source="sketchfab"`): its own search API ignores the query text entirely
  (verified live - a nonsense query and a real one return the same result set, even
  authenticated). `search_assets` is only useful for *browsing* Sketchfab, never for finding a
  specific named model.
- **For a specific Sketchfab model** (a named character, prop, vehicle, etc.), call
  `web_search_assets(query=...)` instead - it uses real web search (SearXNG, DuckDuckGo fallback)
  to find the actual model page and extract its UID. It returns items with `id="sketchfab:<uid>"`
  ready to pass straight to `download_and_import_asset(asset_id=...)`.
- `search_assets(downloadable_only=True)` (the default) silently drops Sketchfab results that need
  `SKETCHFAB_API_TOKEN` but don't have one configured - it reports how many were hidden as a
  warning, not visibly. Check `warnings` before concluding a search "found nothing."
- Without `SKETCHFAB_API_TOKEN` configured, Sketchfab downloads can't be resolved at all -
  `download_and_import_asset` fails with an explicit error naming the missing token, it does not
  silently no-op.

### Downloading and importing

- Pass either `url` (a direct file link) or `asset_id` (e.g. `"ambientcg:3DApple002"`,
  `"sketchfab:<uid>"`) to `download_and_import_asset` - not both.
- Supported formats: `.fbx`, `.obj`, `.gltf`, `.glb`, textures (`.png`/`.jpg`/`.jpeg`/`.tga`/
  `.exr`/`.hdr`), and `.zip` archives of those. `.bin` and `.mtl` files inside an archive are not
  standalone assets but required companions (a non-binary glTF's mesh/skin data lives in an
  external `.bin`; an OBJ's material assignment lives in its `.mtl`) - seeing them in
  `extracted_files` is expected, not a bug.
- **glTF/GLB needs a Unity package to actually import.** Sketchfab's default export format is
  glTF, but vanilla Unity has no built-in glTF importer - only `.fbx`/`.obj` work out of the box.
  If the target Unity project doesn't have a glTF importer (e.g. `com.unity.cloud.gltfast`)
  installed, `download_and_import_asset` fails with an explicit error rather than silently
  importing nothing. Add it to the project's `Packages/manifest.json` and let Unity resolve it,
  then retry.

### Verifying an import actually worked

`download_and_import_asset` returning `success=true` means Unity registered *some* asset at that
path - it does not by itself prove the file was understood. Always follow up with
`inspect_imported_asset(asset_path=...)` before treating a model as usable:

- `asset_type` should be a real type (e.g. `GameObject` for a model). A file Unity has no importer
  for still gets registered as an opaque, empty placeholder rather than failing outright - Visora
  rejects that case for the main import path already, but re-check whenever a format isn't in the
  supported list above, or when going through raw Unity bridge calls that bypass Visora's own
  validation.
- `submesh_count > 0` and a non-empty `materials` list confirm real geometry was parsed, not just a
  copied file.
- Use `instantiate_scene_asset` + `screenshot`/`diagnose_camera_framing` for a final visual check -
  a model can import correctly but still be tiny, far from the camera, or oriented sideways (a
  property of the source asset's own export, not an import bug).
