# State and safety

Unity Editor is a stateful process. A request can trigger script compilation, domain reload, asset import, Play Mode transition, scene dirtiness, Animation Mode, temporary cameras, or modified global render settings. Visora treats those transitions as part of the operation rather than incidental side effects.

<p align="center">
  <img src="../assets/state-safety.jpg" alt="A Unity scene is enclosed by a protective transaction boundary with preflight, scoped change, rollback, and visual verification" width="100%">
</p>
<p align="center"><em>Safety is a lifecycle: preflight, scoped mutation, recovery handle, restoration, and proof.</em></p>

## Safety model

Safety is layered:

1. **Preflight:** verify bridge, editor mode, compilation/import state, target paths, and capability.
2. **Scope:** change the smallest set of objects and use explicit operation IDs where supported.
3. **Recovery handle:** create an Undo group, backup, or state snapshot before mutation.
4. **Execution:** avoid automatic replay when the request may already have reached Unity.
5. **Restoration:** restore temporary state in `finally`/failure paths.
6. **Verification:** re-inspect the result before saving or declaring success.

No layer makes arbitrary editor code risk-free. Together they make failure observable and recovery practical.

## Editor state

`get_editor_state` reports:

- Play and pause state;
- script compilation and asset-update state;
- whether the Editor is idle;
- active scene name/path and dirty state where available;
- loaded scene count;
- wait duration and timeout state when polling.

Use `wait=true` before a mutation when compilation or import is expected. A bridge connection can temporarily disappear during domain reload; the polling and transport layers are designed to treat that as a transient state rather than immediate proof that Unity is gone.

## Edit Mode and Play Mode

Play Mode is not a harmless rendering toggle. Entering or leaving it can reload the scripting domain, destroy runtime objects, restore serialized scene state, and interrupt the HTTP bridge.

Rules enforced by the backend include:

- clip authoring requires Edit Mode;
- `preview_animation` samples authored clips in Edit Mode and rejects Play Mode;
- general `game_camera` capture may enter Play Mode temporarily and must return to the original mode;
- scene reload from disk is blocked in Play Mode;
- scene save is blocked in Play Mode unless the caller uses the explicit dangerous override;
- automatic transaction saves are skipped in Play Mode and returned as warnings.

Use `playmode_management` instead of toggling the Editor through arbitrary C#. It waits around the transition and tolerates bridge rebinding.

## Generic scene transaction

`safe_transaction` is the escape hatch for editor work without a dedicated tool. Its normal lifecycle is:

```text
read editor state
  -> wait for compilation when necessary
  -> optional pre-save in Edit Mode
  -> optional named Undo group
  -> execute statement-body C#
  -> inspect outer execution and compiler diagnostics
  -> rollback Undo group on failure when requested
  -> optional post-save in Edit Mode
  -> return transaction_id, undo_group, logs, diagnostics, and recovery status
```

Important limitations:

- The caller’s C# must register affected Unity objects with Undo for rollback to be complete.
- A registered group is a recovery boundary, not a database transaction.
- File writes and external side effects are not reverted by Unity Undo.
- If the HTTP read times out, the backend does not replay the code because Unity may already have executed it.
- `auto_save=true` can persist unrelated dirty scene changes; it should be used only when that is intentional.

The returned `transaction_id` identifies the Visora operation. `undo_group` is the Unity recovery handle. `rolled_back=true` confirms that Visora invoked its rollback path, not that every arbitrary external effect was reversed.

## Restore choices

`restore_scene_state` exposes two different mechanisms:

| Mechanism | Scope | Risk |
| --- | --- | --- |
| `undo_group` | Reverts Unity changes recorded in or after the group | Depends on correct Undo registration |
| `reload_active_scene=true` | Discards all unsaved changes by reopening the scene from disk | Destructive to unrelated unsaved work |

Prefer targeted Undo. Scene reload is a deliberate recovery action, is blocked in Play Mode, and should only be used when discarding all unsaved scene changes is acceptable.

## Saving

`save_scene` first verifies editor state.

- In Play Mode, it fails by default because runtime objects could be serialized unintentionally.
- During compilation, it fails rather than racing the domain reload.
- `force_during_play_mode=true` bypasses the first guard and produces a warning. It is not a routine workflow option.
- A requested Save As path is executed through Unity’s scene APIs; the backend returns the resulting scene path and dirty/saved state.

Saving is persistence, not verification. Run the relevant diagnostic before saving.

## Animation mutation

Animation authoring has stricter behavior than generic scene editing:

- require Edit Mode before writing;
- operate through typed transaction operations;
- use operation IDs for idempotent native writes;
- create pre-mutation clip backups for supported authoring operations;
- keep backups under `VisoraBackups/` in the Unity project;
- expose `list_animation_backups` and `restore_animation_clip`;
- use non-destructive output clips for contact baking where applicable;
- verify changes over time with `preview_animation`, not a static screenshot.

`edit_animation_transaction` groups multiple typed operations so related keys, holds, and events can share an atomic workflow and authoritative timing. For action beats, use one impact timestamp for character pose, hit-stop, camera response, and events.

## Preview and capture state

Visual diagnostics may temporarily change:

- camera selection or create an auto-framing camera;
- target pose or Animation Mode;
- render texture and camera target;
- ambient lighting or a temporary diagnostic light rig;
- Play Mode;
- sampled frame time.

Native stepped routines run one at a time to prevent two captures from interleaving state snapshots. Services should restore all temporary state on completion and exception. Tool results surface restoration evidence such as pose restoration, scene dirtiness, dropped frames, or auto-frame cleanup.

Treat missing restoration confirmation as a warning that requires inspection. Do not save a scene dirtied only by a diagnostic preview.

## Asset mutations

Asset import changes both the filesystem and Unity’s `AssetDatabase`. The asset pipeline therefore:

- stages remote content outside `Assets`;
- proves the destination remains inside the target project’s `Assets` directory;
- never overwrites an existing file, using a suffixed destination instead;
- disables timeout replay for import and instantiation calls;
- removes the newly copied path and `.meta` sidecar after a failed import;
- requires Unity to report concrete imported objects;
- recommends a follow-up `inspect_imported_asset` before scene use.

See [Asset pipeline](ASSET_PIPELINE.md) for the full security model.

## Idempotency and retry decisions

Before adding a write operation, classify it:

| Operation property | Retry after connection failure | Retry after read timeout |
| --- | --- | --- |
| Pure read | Usually safe | Usually safe if the caller owns the timeout policy |
| Write with server-side operation ID | Safe only if the server guarantees deduplication | Possibly, but inspect the guarantee explicitly |
| Write without idempotency | Only when failure proves it did not reach Unity | No |
| Play Mode transition | Use state polling, not blind replay | Inspect current mode first |
| Asset import/instantiate | Re-inspect asset/scene first | No automatic replay |

The shared bridge defaults are not a substitute for this classification. Pass `retry_on_timeout=False` for non-idempotent requests.

## Verification patterns

| Change | Minimum verification |
| --- | --- |
| Scene transform/material edit | Re-query state plus screenshot or framing diagnostic |
| Camera edit | `diagnose_camera_framing` and `project_world_points`, then screenshot |
| Imported model | `inspect_imported_asset`; require a real asset type and geometry |
| Rig/Avatar change | `skeleton_mapper` or `validate_humanoid_avatar` |
| Clip key/event edit | `inspect_animation_clip` plus `preview_animation` |
| Contact/IK change | Contact analysis across the affected time range plus preview |
| Mesh repair | Re-run `skinned_mesh_diagnostics` and compare issue categories |

The [Agent workflows](../AGENT_WORKFLOWS.md) provide complete sequences.
