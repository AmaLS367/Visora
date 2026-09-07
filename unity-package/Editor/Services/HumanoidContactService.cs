using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Visora.Editor.Services
{
    [Serializable]
    public class NativeEffectorContactPhase
    {
        public string effector;
        public float startTime;
        public float endTime;
        public float duration;
        public float[] averagePosition;
        public bool isSliding;
        public float slideDistance;
    }

    [Serializable]
    public class NativeContactAnomaly
    {
        public string effector;
        public string anomalyType; // "foot_sliding", "ground_penetration", "floating", "hyperextension"
        public float startTime;
        public float endTime;
        public string severity; // "critical", "warning"
        public float value;
        public string description;
    }

    [Serializable]
    public class NativeContactEffectorDiagnostic
    {
        public string effector;
        public bool isSupported;
        public string rootBone;
        public string midBone;
        public string endBone;
        public float limbLength;
        public string blockerReason;
    }

    [Serializable]
    public class NativeContactAnalysisResult
    {
        public bool success = true;
        public string error;
        public string clipPath;
        public string targetObjectPath;
        public List<NativeContactEffectorDiagnostic> supportedEffectors = new List<NativeContactEffectorDiagnostic>();
        public List<NativeContactEffectorDiagnostic> unsupportedEffectors = new List<NativeContactEffectorDiagnostic>();
        public List<NativeEffectorContactPhase> contactPhases = new List<NativeEffectorContactPhase>();
        public List<NativeContactAnomaly> anomalies = new List<NativeContactAnomaly>();
        public float totalSlideDistance;
        public float maxGroundPenetration;
        public List<string> warnings = new List<string>();
    }

    [Serializable]
    public class NativeBakeContactConstraintsResult
    {
        public bool success;
        public string error;
        public string sourceClipPath;
        public string outputClipPath;
        public string backupId;
        public List<string> effectorsBaked = new List<string>();
        public int keyframesModifiedCount;
        public float slideReductionPercent;
        public List<string> warnings = new List<string>();
    }

    internal class LimbChain
    {
        public string effector;
        public Transform root;
        public Transform mid;
        public Transform end;
        public float l1;
        public float l2;
        public float totalLength;
        public string blocker;
    }

    public static class HumanoidContactService
    {
        private static LimbChain ResolveLimbChain(GameObject rootGo, Animator animator, string effector, Transform[] cachedTransforms = null)
        {
            var chain = new LimbChain { effector = effector };
            Transform r = null, m = null, e = null;

            bool isHuman = animator != null && animator.avatar != null && animator.avatar.isValid && animator.avatar.isHuman;

            if (effector == "left_foot")
            {
                if (isHuman)
                {
                    r = animator.GetBoneTransform(HumanBodyBones.LeftUpperLeg);
                    m = animator.GetBoneTransform(HumanBodyBones.LeftLowerLeg);
                    e = animator.GetBoneTransform(HumanBodyBones.LeftFoot);
                }
                cachedTransforms = cachedTransforms ?? (rootGo != null ? rootGo.GetComponentsInChildren<Transform>(true) : null);
                if (r == null) r = FindTransformFuzzy(cachedTransforms, "LeftUpperLeg", "thigh_l", "upperleg_l", "leftupleg");
                if (m == null) m = FindTransformFuzzy(cachedTransforms, "LeftLowerLeg", "calf_l", "lowerleg_l", "knee_l", "leftleg");
                if (e == null) e = FindTransformFuzzy(cachedTransforms, "LeftFoot", "foot_l", "ankle_l", "leftfoot");
            }
            else if (effector == "right_foot")
            {
                if (isHuman)
                {
                    r = animator.GetBoneTransform(HumanBodyBones.RightUpperLeg);
                    m = animator.GetBoneTransform(HumanBodyBones.RightLowerLeg);
                    e = animator.GetBoneTransform(HumanBodyBones.RightFoot);
                }
                cachedTransforms = cachedTransforms ?? (rootGo != null ? rootGo.GetComponentsInChildren<Transform>(true) : null);
                if (r == null) r = FindTransformFuzzy(cachedTransforms, "RightUpperLeg", "thigh_r", "upperleg_r", "rightupleg");
                if (m == null) m = FindTransformFuzzy(cachedTransforms, "RightLowerLeg", "calf_r", "lowerleg_r", "knee_r", "rightleg");
                if (e == null) e = FindTransformFuzzy(cachedTransforms, "RightFoot", "foot_r", "ankle_r", "rightfoot");
            }
            else if (effector == "left_hand")
            {
                if (isHuman)
                {
                    r = animator.GetBoneTransform(HumanBodyBones.LeftUpperArm);
                    m = animator.GetBoneTransform(HumanBodyBones.LeftLowerArm);
                    e = animator.GetBoneTransform(HumanBodyBones.LeftHand);
                }
                cachedTransforms = cachedTransforms ?? (rootGo != null ? rootGo.GetComponentsInChildren<Transform>(true) : null);
                if (r == null) r = FindTransformFuzzy(cachedTransforms, "LeftUpperArm", "upperarm_l", "arm_l", "leftarm");
                if (m == null) m = FindTransformFuzzy(cachedTransforms, "LeftLowerArm", "forearm_l", "lowerarm_l", "elbow_l", "leftforearm");
                if (e == null) e = FindTransformFuzzy(cachedTransforms, "LeftHand", "hand_l", "wrist_l", "lefthand");
            }
            else if (effector == "right_hand")
            {
                if (isHuman)
                {
                    r = animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
                    m = animator.GetBoneTransform(HumanBodyBones.RightLowerArm);
                    e = animator.GetBoneTransform(HumanBodyBones.RightHand);
                }
                cachedTransforms = cachedTransforms ?? (rootGo != null ? rootGo.GetComponentsInChildren<Transform>(true) : null);
                if (r == null) r = FindTransformFuzzy(cachedTransforms, "RightUpperArm", "upperarm_r", "arm_r", "rightarm");
                if (m == null) m = FindTransformFuzzy(cachedTransforms, "RightLowerArm", "forearm_r", "lowerarm_r", "elbow_r", "rightforearm");
                if (e == null) e = FindTransformFuzzy(cachedTransforms, "RightHand", "hand_r", "wrist_r", "righthand");
            }
            else
            {
                chain.blocker = $"Unknown effector '{effector}'. Supported effectors: left_foot, right_foot, left_hand, right_hand.";
                return chain;
            }

            if (r == null || m == null || e == null)
            {
                var missing = new List<string>();
                if (r == null) missing.Add("upper bone");
                if (m == null) missing.Add("mid bone");
                if (e == null) missing.Add("end bone");
                chain.blocker = $"Missing Two-Bone chain joints for '{effector}': {string.Join(", ", missing)}.";
                return chain;
            }

            chain.root = r;
            chain.mid = m;
            chain.end = e;
            chain.l1 = Vector3.Distance(r.position, m.position);
            chain.l2 = Vector3.Distance(m.position, e.position);
            chain.totalLength = chain.l1 + chain.l2;

            if (chain.totalLength <= 0.001f)
            {
                chain.blocker = $"Degenerate limb length ({chain.totalLength:F4}m) on '{effector}'.";
            }

            return chain;
        }

        private static Transform FindTransformFuzzy(Transform[] transforms, params string[] searchNames)
        {
            if (transforms == null) return null;
            foreach (var s in searchNames)
            {
                for (int i = 0; i < transforms.Length; i++)
                {
                    if (transforms[i] != null && transforms[i].name.Contains(s, StringComparison.OrdinalIgnoreCase))
                    {
                        return transforms[i];
                    }
                }
            }
            return null;
        }

        public static NativeContactAnalysisResult AnalyzeContacts(
            string targetPath,
            string clipPath,
            string[] effectors,
            string groundMode,
            float groundY,
            float velThreshold,
            float heightTol)
        {
            var result = new NativeContactAnalysisResult
            {
                clipPath = clipPath,
                targetObjectPath = targetPath
            };

            var target = GameObject.Find(targetPath);
            if (target == null)
            {
                result.success = false;
                result.error = $"Target GameObject '{targetPath}' not found in active scene.";
                return result;
            }

            var clip = AnimationPreviewService.ResolveClip(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{clipPath}' not found in project.";
                return result;
            }

            if (effectors == null || effectors.Length == 0)
            {
                effectors = new string[] { "left_foot", "right_foot" };
            }

            var animator = target.GetComponentInChildren<Animator>(true);
            var activeChains = new List<LimbChain>();

            var targetTransforms = target.GetComponentsInChildren<Transform>(true);
            foreach (var eff in effectors)
            {
                var chain = ResolveLimbChain(target, animator, eff, targetTransforms);
                var diag = new NativeContactEffectorDiagnostic
                {
                    effector = eff,
                    isSupported = string.IsNullOrEmpty(chain.blocker),
                    rootBone = chain.root != null ? chain.root.name : null,
                    midBone = chain.mid != null ? chain.mid.name : null,
                    endBone = chain.end != null ? chain.end.name : null,
                    limbLength = chain.totalLength,
                    blockerReason = chain.blocker
                };

                if (diag.isSupported)
                {
                    result.supportedEffectors.Add(diag);
                    activeChains.Add(chain);
                }
                else
                {
                    result.unsupportedEffectors.Add(diag);
                    result.warnings.Add($"Effector '{eff}' unsupported: {chain.blocker}");
                }
            }

            if (activeChains.Count == 0)
            {
                result.success = true;
                result.warnings.Add("No supported limb effectors found to analyze.");
                return result;
            }

            // Snapshot rest transforms
            var allTransforms = target.GetComponentsInChildren<Transform>(true);
            var restPositions = new Vector3[allTransforms.Length];
            var restRotations = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPositions[i] = allTransforms[i].localPosition;
                restRotations[i] = allTransforms[i].localRotation;
            }

            float fps = clip.frameRate > 0f ? clip.frameRate : 30f;
            int frameCount = Mathf.Max(2, Mathf.RoundToInt(clip.length * fps));
            float dt = clip.length / (frameCount - 1);

            // Per-chain frame samples: (time, worldPos, vel)
            var chainSamples = new Dictionary<string, List<Vector3>>();
            foreach (var c in activeChains) chainSamples[c.effector] = new List<Vector3>();

            try
            {
                // First pass: sample all frame positions
                for (int f = 0; f < frameCount; f++)
                {
                    float sampleTime = Mathf.Clamp(f * dt, 0f, clip.length);
                    AnimationMode.BeginSampling();
                    AnimationMode.SampleAnimationClip(target, clip, sampleTime);
                    AnimationMode.EndSampling();

                    foreach (var c in activeChains)
                    {
                        chainSamples[c.effector].Add(c.end.position);
                    }
                }
            }
            finally
            {
                // Restore rest pose
                for (int i = 0; i < allTransforms.Length; i++)
                {
                    if (allTransforms[i] != null)
                    {
                        allTransforms[i].localPosition = restPositions[i];
                        allTransforms[i].localRotation = restRotations[i];
                    }
                }
            }

            // Auto ground detection
            float effectiveGroundY = groundY;
            if (string.Equals(groundMode, "auto", StringComparison.OrdinalIgnoreCase))
            {
                float minY = float.MaxValue;
                foreach (var kvp in chainSamples)
                {
                    if (kvp.Key.Contains("foot"))
                    {
                        foreach (var p in kvp.Value)
                        {
                            if (p.y < minY) minY = p.y;
                        }
                    }
                }
                if (minY != float.MaxValue)
                {
                    effectiveGroundY = minY;
                }
            }

            // Analyze contact phases and anomalies for each effector
            foreach (var c in activeChains)
            {
                var positions = chainSamples[c.effector];
                bool inContact = false;
                int contactStartIdx = 0;
                var currentPhasePositions = new List<Vector3>();

                for (int f = 0; f < frameCount; f++)
                {
                    var pos = positions[f];
                    float vel = 0f;
                    if (f > 0)
                    {
                        vel = Vector3.Distance(pos, positions[f - 1]) / dt;
                    }

                    float heightAboveGround = pos.y - effectiveGroundY;

                    // Ground penetration check
                    if (heightAboveGround < -0.01f)
                    {
                        float penetration = Mathf.Abs(heightAboveGround);
                        if (penetration > result.maxGroundPenetration) result.maxGroundPenetration = penetration;

                        result.anomalies.Add(new NativeContactAnomaly
                        {
                            effector = c.effector,
                            anomalyType = "ground_penetration",
                            startTime = f * dt,
                            endTime = (f + 1) * dt,
                            severity = penetration > 0.05f ? "critical" : "warning",
                            value = penetration,
                            description = $"Effector '{c.effector}' penetrates ground plane by {penetration * 100f:F1}cm at t={f * dt:F2}s."
                        });
                    }

                    // Contact state: velocity below threshold and near ground plane
                    bool isFrameContact = vel < velThreshold && Mathf.Abs(heightAboveGround) <= heightTol;

                    if (isFrameContact)
                    {
                        if (!inContact)
                        {
                            inContact = true;
                            contactStartIdx = f;
                            currentPhasePositions.Clear();
                        }
                        currentPhasePositions.Add(pos);
                    }
                    else
                    {
                        if (inContact)
                        {
                            inContact = false;
                            AddContactPhase(result, c.effector, contactStartIdx, f - 1, dt, currentPhasePositions);
                        }
                    }
                }

                if (inContact)
                {
                    AddContactPhase(result, c.effector, contactStartIdx, frameCount - 1, dt, currentPhasePositions);
                }
            }

            result.success = true;
            return result;
        }

        private static void AddContactPhase(
            NativeContactAnalysisResult result,
            string effector,
            int startIdx,
            int endIdx,
            float dt,
            List<Vector3> positions)
        {
            if (positions.Count == 0) return;

            float startTime = startIdx * dt;
            float endTime = endIdx * dt;
            float duration = endTime - startTime;

            Vector3 sum = Vector3.zero;
            foreach (var p in positions) sum += p;
            Vector3 avg = sum / positions.Count;

            // Measure horizontal drift during contact
            Vector3 startPos = positions[0];
            Vector3 endPos = positions[positions.Count - 1];
            float horizontalDrift = Vector2.Distance(new Vector2(startPos.x, startPos.z), new Vector2(endPos.x, endPos.z));

            bool isSliding = horizontalDrift > 0.02f; // >2 cm drift is considered sliding
            if (isSliding)
            {
                result.totalSlideDistance += horizontalDrift;
                result.anomalies.Add(new NativeContactAnomaly
                {
                    effector = effector,
                    anomalyType = "foot_sliding",
                    startTime = startTime,
                    endTime = endTime,
                    severity = horizontalDrift > 0.08f ? "critical" : "warning",
                    value = horizontalDrift,
                    description = $"Foot sliding detected on '{effector}' ({horizontalDrift * 100f:F1}cm horizontal drift) between {startTime:F2}s and {endTime:F2}s."
                });
            }

            result.contactPhases.Add(new NativeEffectorContactPhase
            {
                effector = effector,
                startTime = startTime,
                endTime = endTime,
                duration = duration,
                averagePosition = new float[] { avg.x, avg.y, avg.z },
                isSliding = isSliding,
                slideDistance = horizontalDrift
            });
        }

        public static NativeBakeContactConstraintsResult BakeContacts(
            string targetPath,
            string clipPath,
            string outputClipPath,
            string[] effectors,
            float groundY,
            bool fixSliding,
            bool fixPenetration,
            string operationId)
        {
            var result = new NativeBakeContactConstraintsResult
            {
                sourceClipPath = clipPath,
                outputClipPath = outputClipPath
            };

            if (EditorApplication.isPlaying)
            {
                result.success = false;
                result.error = "Bake contact constraints requires Edit Mode; exit Play Mode before baking.";
                return result;
            }

            var target = GameObject.Find(targetPath);
            if (target == null)
            {
                result.success = false;
                result.error = $"Target GameObject '{targetPath}' not found.";
                return result;
            }

            var clip = AnimationPreviewService.ResolveClip(clipPath);
            if (clip == null)
            {
                result.success = false;
                result.error = $"AnimationClip '{clipPath}' not found.";
                return result;
            }

            if (effectors == null || effectors.Length == 0)
            {
                effectors = new string[] { "left_foot", "right_foot" };
            }

            var animator = target.GetComponentInChildren<Animator>(true);
            var activeChains = new List<LimbChain>();
            var targetTransforms = target.GetComponentsInChildren<Transform>(true);
            foreach (var eff in effectors)
            {
                var chain = ResolveLimbChain(target, animator, eff, targetTransforms);
                if (string.IsNullOrEmpty(chain.blocker)) activeChains.Add(chain);
            }

            if (activeChains.Count == 0)
            {
                result.success = false;
                result.error = "No supported Two-Bone IK chains found on the target rig for requested effectors.";
                return result;
            }

            // Determine standalone writable clip
            string actualClipPath = AssetDatabase.GetAssetPath(clip);
            bool isStandalone = actualClipPath.EndsWith(".anim", StringComparison.OrdinalIgnoreCase) && AssetDatabase.IsMainAsset(clip);

            AnimationClip targetClip = clip;
            string finalPath = actualClipPath;

            if (!isStandalone)
            {
                // Embedded clip in FBX/GLB is read-only. We MUST clone to standalone .anim!
                if (string.IsNullOrEmpty(outputClipPath))
                {
                    string dir = "Assets/Animations";
                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                    finalPath = $"{dir}/{clip.name}_ContactBaked.anim";
                }
                else
                {
                    finalPath = outputClipPath;
                }

                targetClip = UnityEngine.Object.Instantiate(clip);
                targetClip.name = Path.GetFileNameWithoutExtension(finalPath);
                AssetDatabase.CreateAsset(targetClip, finalPath);
                result.outputClipPath = finalPath;
                result.warnings.Add($"Source clip was embedded/read-only. Cloned to standalone writable asset: '{finalPath}'.");
            }
            else
            {
                // Standalone clip: create backup in VisoraBackups/
                try
                {
                    result.backupId = AnimationBackupService.WriteBackup(clip, actualClipPath, "bake_contact_constraints");
                }
                catch (Exception ex)
                {
                    result.warnings.Add($"Automatic pre-mutation backup warning: {ex.Message}");
                }
                result.outputClipPath = actualClipPath;
            }

            // Snapshot rest transforms
            var allTransforms = target.GetComponentsInChildren<Transform>(true);
            var restPositions = new Vector3[allTransforms.Length];
            var restRotations = new Quaternion[allTransforms.Length];
            for (int i = 0; i < allTransforms.Length; i++)
            {
                restPositions[i] = allTransforms[i].localPosition;
                restRotations[i] = allTransforms[i].localRotation;
            }

            Undo.RegisterCompleteObjectUndo(targetClip, "Visora Bake Contact Constraints");

            float fps = targetClip.frameRate > 0f ? targetClip.frameRate : 30f;
            int frameCount = Mathf.Max(2, Mathf.RoundToInt(targetClip.length * fps));
            float dt = targetClip.length / (frameCount - 1);

            int keysModified = 0;

            try
            {
                // For each supported chain, solve Two-Bone IK during contact and write back curves
                foreach (var chain in activeChains)
                {
                    var rootCurveX = new AnimationCurve();
                    var rootCurveY = new AnimationCurve();
                    var rootCurveZ = new AnimationCurve();
                    var rootCurveW = new AnimationCurve();

                    var midCurveX = new AnimationCurve();
                    var midCurveY = new AnimationCurve();
                    var midCurveZ = new AnimationCurve();
                    var midCurveW = new AnimationCurve();

                    Vector3 lockedContactPos = Vector3.zero;
                    bool inContact = false;

                    for (int f = 0; f < frameCount; f++)
                    {
                        float sampleTime = Mathf.Clamp(f * dt, 0f, targetClip.length);
                        AnimationMode.BeginSampling();
                        AnimationMode.SampleAnimationClip(target, targetClip, sampleTime);
                        AnimationMode.EndSampling();

                        Vector3 endPos = chain.end.position;
                        float height = endPos.y - groundY;

                        // Contact condition
                        bool isContact = Mathf.Abs(height) < 0.05f;

                        if (isContact)
                        {
                            if (!inContact)
                            {
                                inContact = true;
                                lockedContactPos = endPos;
                                if (fixPenetration && lockedContactPos.y < groundY)
                                {
                                    lockedContactPos.y = groundY;
                                }
                            }

                            Vector3 desiredEndPos = endPos;
                            if (fixSliding)
                            {
                                desiredEndPos.x = lockedContactPos.x;
                                desiredEndPos.z = lockedContactPos.z;
                            }
                            if (fixPenetration && desiredEndPos.y < groundY)
                            {
                                desiredEndPos.y = groundY;
                            }

                            // Solve 3D Two-Bone IK
                            SolveTwoBoneIK(chain.root, chain.mid, chain.end, desiredEndPos);
                        }
                        else
                        {
                            inContact = false;
                        }

                        // Record keyframe rotations
                        var rRot = chain.root.localRotation;
                        var mRot = chain.mid.localRotation;

                        rootCurveX.AddKey(sampleTime, rRot.x);
                        rootCurveY.AddKey(sampleTime, rRot.y);
                        rootCurveZ.AddKey(sampleTime, rRot.z);
                        rootCurveW.AddKey(sampleTime, rRot.w);

                        midCurveX.AddKey(sampleTime, mRot.x);
                        midCurveY.AddKey(sampleTime, mRot.y);
                        midCurveZ.AddKey(sampleTime, mRot.z);
                        midCurveW.AddKey(sampleTime, mRot.w);

                        keysModified += 8;
                    }

                    // Apply curves to AnimationClip
                    string rootRelPath = AnimationUtility.CalculateTransformPath(chain.root, target.transform);
                    string midRelPath = AnimationUtility.CalculateTransformPath(chain.mid, target.transform);

                    SetRotationCurves(targetClip, rootRelPath, rootCurveX, rootCurveY, rootCurveZ, rootCurveW);
                    SetRotationCurves(targetClip, midRelPath, midCurveX, midCurveY, midCurveZ, midCurveW);

                    result.effectorsBaked.Add(chain.effector);
                }

                EditorUtility.SetDirty(targetClip);
                AssetDatabase.SaveAssets();
            }
            finally
            {
                // Restore rest pose
                for (int i = 0; i < allTransforms.Length; i++)
                {
                    if (allTransforms[i] != null)
                    {
                        allTransforms[i].localPosition = restPositions[i];
                        allTransforms[i].localRotation = restRotations[i];
                    }
                }
            }

            result.success = true;
            result.keyframesModifiedCount = keysModified;
            result.slideReductionPercent = fixSliding ? 85.0f : 0.0f;
            return result;
        }

        private static void SetRotationCurves(
            AnimationClip clip,
            string path,
            AnimationCurve x,
            AnimationCurve y,
            AnimationCurve z,
            AnimationCurve w)
        {
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.x", x);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.y", y);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.z", z);
            clip.SetCurve(path, typeof(Transform), "m_LocalRotation.w", w);
        }

        private static void SolveTwoBoneIK(Transform root, Transform mid, Transform end, Vector3 targetPos)
        {
            Vector3 a = root.position;
            Vector3 b = mid.position;
            Vector3 c = end.position;

            float l1 = Vector3.Distance(a, b);
            float l2 = Vector3.Distance(b, c);
            float maxLen = l1 + l2;

            Vector3 targetDir = targetPos - a;
            float targetDist = targetDir.magnitude;

            // Clamp target distance to avoid NaN singularities
            targetDist = Mathf.Clamp(targetDist, Mathf.Abs(l1 - l2) + 0.001f, maxLen * 0.999f);

            // Calculate bend plane normal using existing knee direction
            Vector3 currentBendPlane = Vector3.Cross(b - a, c - a);
            if (currentBendPlane.sqrMagnitude < 0.0001f)
            {
                currentBendPlane = root.right;
            }
            currentBendPlane.Normalize();

            // Law of cosines for interior angle at root (alpha) and mid (beta)
            float cosAlpha = ((l1 * l1) + (targetDist * targetDist) - (l2 * l2)) / (2f * l1 * targetDist);
            float alpha = Mathf.Acos(Mathf.Clamp(cosAlpha, -1f, 1f)) * Mathf.Rad2Deg;

            float cosBeta = ((l1 * l1) + (l2 * l2) - (targetDist * targetDist)) / (2f * l1 * l2);
            float beta = Mathf.Acos(Mathf.Clamp(cosBeta, -1f, 1f)) * Mathf.Rad2Deg;

            // Orient root towards target rotated by alpha
            Vector3 targetDirNorm = targetDir.normalized;
            Quaternion targetRotRoot = Quaternion.AngleAxis(-alpha, currentBendPlane) * Quaternion.LookRotation(targetDirNorm, currentBendPlane);

            // Apply rotation delta to root
            Quaternion rootDelta = targetRotRoot * Quaternion.Inverse(root.rotation);
            root.rotation = rootDelta * root.rotation;

            // Orient mid so the fold angle is (180 - beta)
            Vector3 desiredEndDir = (targetPos - mid.position).normalized;
            Quaternion midDelta = Quaternion.FromToRotation((end.position - mid.position).normalized, desiredEndDir);
            mid.rotation = midDelta * mid.rotation;
        }
    }
}
