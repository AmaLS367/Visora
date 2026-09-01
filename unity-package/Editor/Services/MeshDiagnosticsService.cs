using System;
using System.Collections.Generic;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class MeshIssue
    {
        public string type;
        public string severity;
        public string message;
        public string objectName;
    }

    [Serializable]
    public class MeshDiagnosticsResult
    {
        public bool success;
        public string error;
        public string targetName;
        public int vertexCount;
        public int submeshCount;
        public int materialCount;
        public int boneCount;
        public bool hasSkinnedMesh;
        public bool hasMeshFilter;
        public float[] boundsCenter;
        public float[] boundsSize;
        public List<MeshIssue> issues = new List<MeshIssue>();
        public List<string> warnings = new List<string>();
    }

    /// <summary>
    /// Performs non-destructive diagnostics on SkinnedMeshRenderers and MeshFilters.
    /// </summary>
    public static class MeshDiagnosticsService
    {
        public static MeshDiagnosticsResult Diagnose(string targetName = "")
        {
            var result = new MeshDiagnosticsResult { targetName = targetName };

            GameObject targetGo = null;
            if (!string.IsNullOrEmpty(targetName))
            {
                targetGo = GameObject.Find(targetName);
                if (targetGo == null)
                {
                    result.success = false;
                    result.error = $"GameObject '{targetName}' not found in active scene.";
                    return result;
                }
            }

            var smrs = targetGo != null ? targetGo.GetComponentsInChildren<SkinnedMeshRenderer>(true) : UnityEngine.Object.FindObjectsOfType<SkinnedMeshRenderer>();
            var mfs = targetGo != null ? targetGo.GetComponentsInChildren<MeshFilter>(true) : UnityEngine.Object.FindObjectsOfType<MeshFilter>();

            result.hasSkinnedMesh = smrs.Length > 0;
            result.hasMeshFilter = mfs.Length > 0;

            int totalVertices = 0;
            int totalSubmeshes = 0;
            int totalMaterials = 0;
            int totalBones = 0;
            Bounds? combinedBounds = null;

            foreach (var smr in smrs)
            {
                if (smr.sharedMesh == null)
                {
                    result.issues.Add(new MeshIssue
                    {
                        type = "MissingMesh",
                        severity = "Error",
                        message = "SkinnedMeshRenderer has missing sharedMesh",
                        objectName = smr.name
                    });
                    continue;
                }

                var mesh = smr.sharedMesh;
                totalVertices += mesh.vertexCount;
                totalSubmeshes += mesh.subMeshCount;
                totalMaterials += smr.sharedMaterials != null ? smr.sharedMaterials.Length : 0;
                totalBones += smr.bones != null ? smr.bones.Length : 0;

                // Check submesh material count mismatch
                if (smr.sharedMaterials != null && smr.sharedMaterials.Length != mesh.subMeshCount)
                {
                    result.issues.Add(new MeshIssue
                    {
                        type = "MaterialSubmeshMismatch",
                        severity = "Warning",
                        message = $"Material count ({smr.sharedMaterials.Length}) does not match submesh count ({mesh.subMeshCount})",
                        objectName = smr.name
                    });
                }

                // Check null bones
                if (smr.bones != null)
                {
                    for (int b = 0; b < smr.bones.Length; b++)
                    {
                        if (smr.bones[b] == null)
                        {
                            result.issues.Add(new MeshIssue
                            {
                                type = "MissingBoneBinding",
                                severity = "Error",
                                message = $"Bone at index {b} is null or unassigned",
                                objectName = smr.name
                            });
                        }
                    }
                }

                // Bounds
                var bnds = smr.bounds;
                if (!combinedBounds.HasValue) combinedBounds = bnds;
                else combinedBounds.Value.Encapsulate(bnds);

                // Abnormal bounds check
                if (bnds.size.magnitude > 1000f || bnds.size.magnitude < 0.001f)
                {
                    result.issues.Add(new MeshIssue
                    {
                        type = "AbnormalBounds",
                        severity = "Warning",
                        message = $"Suspicious mesh bounds size: {bnds.size}",
                        objectName = smr.name
                    });
                }
            }

            foreach (var mf in mfs)
            {
                if (mf.sharedMesh == null) continue;
                var mesh = mf.sharedMesh;
                totalVertices += mesh.vertexCount;
                totalSubmeshes += mesh.subMeshCount;

                var mr = mf.GetComponent<MeshRenderer>();
                if (mr != null && mr.sharedMaterials != null)
                {
                    totalMaterials += mr.sharedMaterials.Length;
                    if (mr.sharedMaterials.Length != mesh.subMeshCount)
                    {
                        result.issues.Add(new MeshIssue
                        {
                            type = "MaterialSubmeshMismatch",
                            severity = "Warning",
                            message = $"MeshRenderer material count ({mr.sharedMaterials.Length}) does not match submesh count ({mesh.subMeshCount})",
                            objectName = mf.name
                        });
                    }
                }
            }

            result.vertexCount = totalVertices;
            result.submeshCount = totalSubmeshes;
            result.materialCount = totalMaterials;
            result.boneCount = totalBones;

            if (combinedBounds.HasValue)
            {
                var c = combinedBounds.Value.center;
                var s = combinedBounds.Value.size;
                result.boundsCenter = new float[] { c.x, c.y, c.z };
                result.boundsSize = new float[] { s.x, s.y, s.z };
            }

            result.success = true;
            return result;
        }
    }
}
