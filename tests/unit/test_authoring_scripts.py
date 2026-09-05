import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.tools.animation.authoring_scripts import (
    _create_event_code,
    _hold_keyframe_code,
    _list_backups_code,
    _list_keyframes_code,
    _move_keyframe_code,
    _remove_event_code,
    _remove_keyframe_code,
    _restore_backup_code,
    _set_keyframe_code,
)


def test_set_keyframe_code_calls_service() -> None:
    code = _set_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        values=[1.0, 2.0, 3.0],
        tangent_mode="smooth",
        in_tangent=None,
        out_tangent=None,
        operation_id="op-1",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.SetKeyframe(" in code
    assert "Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);" in code
    assert '"Assets/A.anim"' in code
    assert "0.5f" in code
    assert "new float[] { 1.0f, 2.0f, 3.0f }" in code
    assert '"smooth"' in code
    assert '"op-1"' in code


def test_create_event_code_escapes_string_param() -> None:
    code = _create_event_code(
        clip_path="Assets/A.anim",
        time=0.2,
        function_name="OnHit",
        string_param='say "hi"',
        float_param=1.0,
        int_param=0,
        operation_id="op-2",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.CreateEvent(" in code
    assert '\\"hi\\"' in code
    assert '"OnHit"' in code
    assert "0.2f" in code


def test_remove_event_code_passes_null_for_wildcard_function_name() -> None:
    code = _remove_event_code(clip_path="Assets/A.anim", time=0.2, function_name=None, operation_id="op-3")
    assert "Visora.Editor.Services.AnimationAuthoringService.RemoveEvent(" in code
    assert "null" in code
    assert "0.2f" in code


def test_remove_keyframe_code_calls_service() -> None:
    code = _remove_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        operation_id="op-4",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.RemoveKeyframe(" in code
    assert "0.5f" in code
    assert '"op-4"' in code


def test_move_keyframe_code_calls_service() -> None:
    code = _move_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        from_time=0.5,
        to_time=1.0,
        operation_id="op-move",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.MoveKeyframe(" in code
    assert "0.5f" in code
    assert "1.0f" in code


def test_hold_keyframe_code_calls_service_with_eight_arguments() -> None:
    code = _hold_keyframe_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        hold_until=1.5,
        value=[1.0, 2.0, 3.0],
        operation_id="op-hold",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.SetKeyframeHold(" in code
    assert "0.5f" in code
    assert "1.5f" in code
    assert "new float[] { 1.0f, 2.0f, 3.0f }" in code


def test_list_keyframes_code_calls_service() -> None:
    code = _list_keyframes_code(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
    )
    assert "Visora.Editor.Services.AnimationAuthoringService.ListKeyframes(" in code
    assert "Visora.Editor.Services.AnimationAuthoringService.ToDictionary(result);" in code


def test_list_backups_and_restore_code_call_service() -> None:
    list_code = _list_backups_code(clip_path="Assets/A.anim")
    restore_code = _restore_backup_code(clip_path="Assets/A.anim", backup_id="x/y.anim", operation_id="op-5")
    assert "Visora.Editor.Services.AnimationBackupService.ListBackups(" in list_code
    assert "Visora.Editor.Services.AnimationBackupServiceDictionaries.ToDictionary(result);" in list_code
    assert "Visora.Editor.Services.AnimationBackupService.RestoreBackup(" in restore_code
    assert "Visora.Editor.Services.AnimationBackupServiceDictionaries.ToDictionary(result);" in restore_code


def test_generated_snippets_compile_against_gate_dll() -> None:
    if shutil.which("dotnet") is None:
        pytest.skip("dotnet SDK is not installed on system")

    repo_root = Path(__file__).resolve().parent.parent.parent
    gate_dll = (
        repo_root / "tools" / "unity-compile-gate" / "bin" / "Debug" / "netstandard2.1" / "Visora.Editor.Gate.dll"
    )
    if not gate_dll.is_file():
        pytest.skip("Visora.Editor.Gate.dll not built; run check_unity_package.py first")

    # Locate Unity managed dir
    managed_dir = Path.home() / "Unity" / "Hub" / "Editor" / "6000.6.0f1" / "Editor" / "Data" / "Managed"
    if not managed_dir.is_dir():
        pytest.skip("Unity Managed directory not found")

    snippets = [
        _list_keyframes_code(
            clip_path="Assets/A.anim",
            target_path="Root",
            type_name="Transform",
            property_name="m_LocalPosition",
        ),
        _set_keyframe_code(
            clip_path="Assets/A.anim",
            target_path="Root",
            type_name="Transform",
            property_name="m_LocalPosition",
            time=0.5,
            values=[1.0, 2.0, 3.0],
            tangent_mode="smooth",
            in_tangent=None,
            out_tangent=None,
            operation_id="op-1",
        ),
        _move_keyframe_code(
            clip_path="Assets/A.anim",
            target_path="Root",
            type_name="Transform",
            property_name="m_LocalPosition",
            from_time=0.5,
            to_time=1.0,
            operation_id="op-2",
        ),
        _remove_keyframe_code(
            clip_path="Assets/A.anim",
            target_path="Root",
            type_name="Transform",
            property_name="m_LocalPosition",
            time=0.5,
            operation_id="op-3",
        ),
        _hold_keyframe_code(
            clip_path="Assets/A.anim",
            target_path="Root",
            type_name="Transform",
            property_name="m_LocalPosition",
            time=0.5,
            hold_until=1.5,
            value=[1.0, 2.0, 3.0],
            operation_id="op-4",
        ),
        _create_event_code(
            clip_path="Assets/A.anim",
            time=0.5,
            function_name="TestEvent",
            string_param="param",
            float_param=1.0,
            int_param=0,
            operation_id="op-5",
        ),
        _remove_event_code(
            clip_path="Assets/A.anim",
            time=0.5,
            function_name="TestEvent",
            operation_id="op-6",
        ),
        _list_backups_code(clip_path="Assets/A.anim"),
        _restore_backup_code(clip_path="Assets/A.anim", backup_id="bk-1", operation_id="op-7"),
    ]

    method_declarations = "\n".join(
        f"    public static object Snippet{i}() {{\n{snip}\n        return null;\n    }}"
        for i, snip in enumerate(snippets)
    )

    csharp_source = f"""using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEditor;

public static class TestGeneratedSnippets
{{
{method_declarations}
}}
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        csproj = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <LangVersion>9.0</LangVersion>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="{gate_dll.resolve()}" />
    <Reference Include="{managed_dir.resolve()}/UnityEditor.dll" />
    <Reference Include="{managed_dir.resolve()}/UnityEngine.dll" />
    <Reference Include="{managed_dir.resolve()}/UnityEngine/*.dll" />
  </ItemGroup>
</Project>"""
        (tmppath / "TestSnippets.csproj").write_text(csproj)
        (tmppath / "TestSnippets.cs").write_text(csharp_source)

        proc = subprocess.run(
            ["dotnet", "build", str(tmppath / "TestSnippets.csproj"), "-c", "Release"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"Compilation failed:\n{proc.stdout}\n{proc.stderr}"
