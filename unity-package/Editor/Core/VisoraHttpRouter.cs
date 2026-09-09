using System;
using System.Collections.Generic;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Visora.Editor.Services;

namespace Visora.Editor.Core
{
    [Serializable]
    public class ExecuteCodeRequest
    {
        public string code;
        public float timeoutSeconds = 60f;
    }

    [Serializable]
    public class PlayModeRequest
    {
        public string action;
    }

    [Serializable]
    public class QueueCancelRequest
    {
        public string ticketId;
    }

    [Serializable]
    public class CameraRenderRequest
    {
        public string cameraName = "Main Camera";
        public int width = 1920;
        public int height = 1080;
        public string format = "PNG";
    }

    [Serializable]
    public class CameraSequenceRequest
    {
        public string cameraName = "Main Camera";
        public int width = 1280;
        public int height = 720;
        public int frameCount = 10;
        public float frameIntervalSeconds = 0.1f;
    }

    [Serializable]
    public class DiagnosticCaptureRequest
    {
        public string subjectPath;
        public int width = 1280;
        public int height = 720;
        public int frameCount = 1;
        public float frameIntervalSeconds = 0.1f;
    }

    [Serializable]
    public class AnimationPreviewRequest
    {
        public string cameraName = "Main Camera";
        public string clipPath;
        public string targetObjectPath;
        public int width = 640;
        public int height = 360;
        public int frameCount = 24;
        public float fps = 24f;
        public float startTime;
        public float endTime;
        public bool autoFrame;
    }

    [Serializable]
    public class CameraProjectRequest
    {
        public string cameraName = "Main Camera";
        // Flat x,y,z triples, not float[][]: JsonUtility (Unity's built-in JSON deserializer used
        // just below) cannot deserialize jagged arrays - confirmed by Unity's own serialization
        // analyzer (warning UAC1009) flagging this exact field. Left as float[][], the deserialized
        // request always has points == null regardless of what the client POSTs, so
        // project_world_points silently fails on every call in native mode. See
        // CameraDiagnosticsService.ProjectWorldPoints for the flat-array reconstruction.
        public float[] points;
    }

    [Serializable]
    public class CameraFramingRequest
    {
        public string cameraName = "Main Camera";
        public string subjectPath;
    }

    [Serializable]
    public class MeshDiagnoseRequest
    {
        public string targetName;
    }

    [Serializable]
    public class SkeletonDiagnoseRequest
    {
        public string rootObjectName;
        public string searchQuery;
    }

    [Serializable]
    public class AnimationInspectRequest
    {
        public string clipName;
    }

    [Serializable]
    public class AnimationSampleRequest
    {
        public string clipName;
        public string targetObjectName;
        public float sampleTime;
    }

    [Serializable]
    public class TransactionBeginRequest
    {
        public string description = "Visora Agent Operation";
    }

    [Serializable]
    public class TransactionActionRequest
    {
        public string transactionId;
        public bool saveScene;
    }

    [Serializable]
    public class AssetImportRequest
    {
        public string assetPath;
        public bool allowUnityPackage;
    }

    [Serializable]
    public class AssetInspectRequest
    {
        public string assetPath;
    }

    [Serializable]
    public class AssetInstantiateRequest
    {
        public string assetPath;
        public string parentPath;
        public float[] position;
        public float[] rotation;
        public float[] scale;
        public string name;
    }

    [Serializable]
    public class ClipPathRequest
    {
        public string clipPath;
    }

    [Serializable]
    public class RestoreClipRequest
    {
        public string clipPath;
        public string backupId;
        public string operationId;
    }

    [Serializable]
    public class KeyframeIdentityRequest
    {
        public string clipPath;
        public string targetPath;
        public string typeName;
        public string propertyName;
    }

    [Serializable]
    public class SetKeyframeRequest : KeyframeIdentityRequest
    {
        public float time;
        public float[] values;
        public string tangentMode;
        public float[] inTangent;
        public float[] outTangent;
        public string operationId;
    }

    [Serializable]
    public class MoveKeyframeRequest : KeyframeIdentityRequest
    {
        public float fromTime;
        public float toTime;
        public string operationId;
    }

    [Serializable]
    public class RemoveKeyframeRequest : KeyframeIdentityRequest
    {
        public float time;
        public string operationId;
    }

    [Serializable]
    public class HoldKeyframeRequest : KeyframeIdentityRequest
    {
        public float time;
        public float holdUntil;
        public float[] value;
        public bool hasValue;
        public string operationId;
    }

    [Serializable]
    public class CreateAnimationEventRequest
    {
        public string clipPath;
        public float time;
        public string functionName;
        public string stringParam = "";
        public float floatParam;
        public int intParam;
        public string operationId;
    }

    [Serializable]
    public class RemoveAnimationEventRequest
    {
        public string clipPath;
        public float time;
        public string functionName;
        public string operationId;
    }

    [Serializable]
    public class HumanoidValidateRequest
    {
        public string targetPath;
        public string assetPath;
    }

    [Serializable]
    public class HumanoidConfigureRequest
    {
        public string assetPath;
        public string sourceAvatarPath;
        public string[] boneOverrideKeys;
        public string[] boneOverrideValues;
    }

    [Serializable]
    public class ContactAnalyzeRequest
    {
        public string targetPath;
        public string clipPath;
        public string[] effectors;
        public string groundMode = "plane";
        public float groundY;
        public float velThreshold = 0.05f;
        public float heightTol = 0.05f;
    }

    [Serializable]
    public class ContactBakeRequest
    {
        public string targetPath;
        public string clipPath;
        public string outputClipPath;
        public string[] effectors;
        public float groundY;
        public bool fixSliding = true;
        public bool fixPenetration = true;
        public string operationId;
    }

    [Serializable]
    public class TwoBoneIKRequest
    {
        public string targetPath;
        public string effector;
        public string rootBone;
        public string midBone;
        public string endBone;
        public float[] targetPosition;
        public float[] targetRotation;
        public float[] poleVector;
        public string space = "world";
        public string cameraName = "Main Camera";
        public float weight = 1.0f;
        public bool applyToScene;
        public string bakeToClip;
        public float sampleTime;
        public bool hasSampleTime;
    }

    [Serializable]
    public class ViewportPlacementRequest
    {
        public string cameraName = "Main Camera";
        public string targetPath;
        public string effector;
        public string rootBone;
        public string midBone;
        public string endBone;
        public float viewportX = 0.5f;
        public float viewportY = 0.5f;
        public float cameraDepth = 0.25f;
        public string alignMode = "face_camera";
        public float[] customRotation;
        public float[] poleVector;
        public float weight = 1.0f;
        public bool applyToScene;
        public string bakeToClip;
        public float sampleTime;
        public bool hasSampleTime;
    }

    [Serializable]
    public class CharacterGazeRequest
    {
        public string targetPath;
        public float[] targetLookAtPosition;
        public string targetTransformPath;
        public float chestWeight = 0.15f;
        public float neckWeight = 0.35f;
        public float headWeight = 0.50f;
        public float eyesWeight;
        public float[] upVector;
        public bool applyToScene;
        public string bakeToClip;
        public float sampleTime;
        public bool hasSampleTime;
    }

    [Serializable]
    public class MotionQARequest
    {
        public string clipPath;
        public string targetPath;
        public string[] bones;
        public int sampleFps = 60;
        public float jerkThreshold = 120f;
        public float angularJerkThreshold = 4000f;
    }

    [Serializable]
    public class CurveDiscontinuityRequest
    {
        public string clipPath;
        public string[] filterCurves;
        public bool autoFix;
    }

    public static class VisoraHttpRouter
    {
        public static async Task HandleRequestAsync(HttpListenerContext context)
        {
            var req = context.Request;
            var res = context.Response;

            // CORS headers
            res.AddHeader("Access-Control-Allow-Origin", "*");
            res.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            res.AddHeader("Access-Control-Allow-Headers", "Content-Type");

            if (req.HttpMethod == "OPTIONS")
            {
                res.StatusCode = 200;
                res.Close();
                return;
            }

            string path = req.Url.AbsolutePath.TrimEnd('/');
            string method = req.HttpMethod.ToUpperInvariant();

            try
            {
                string responseJson = "";
                int statusCode = 200;

                if (method == "GET" && (path == "/api/ping" || path == ""))
                {
                    responseJson = JsonUtility.ToJson(new PingResponse
                    {
                        success = true,
                        message = "Visora Editor Bridge active",
                        version = "1.2.0",
                        flavor = "visora-native",
                        unityVersion = Application.unityVersion
                    });
                }
                else if (method == "GET" && path == "/api/visora/info")
                {
                    // GetActiveScene() (and, per Unity's own guard, most other Editor/Scene APIs)
                    // must run on the main thread - this handler runs on HttpListener's threadpool
                    // thread, so calling it bare 500'd every request with "GetActiveScene can only
                    // be called from the main thread." Confirmed live against a real Editor.
                    var info = await MainThreadDispatcher.EnqueueAsync(() => new BridgeInfoResponse
                    {
                        success = true,
                        flavor = "visora-native",
                        version = "1.2.0",
                        apiVersion = 3,
                        unityVersion = Application.unityVersion,
                        isPlaying = EditorApplication.isPlaying,
                        isCompiling = EditorApplication.isCompiling,
                        activeScene = SceneManager.GetActiveScene().name,
                        supportedFeatures = new List<string>
                        {
                            "camera_render",
                            "camera_sequence",
                            "camera_sequence_realtime",
                            "camera_diagnostic",
                            "camera_diagnostic_sequence",
                            "animation_preview_sequence",
                            "animation_preview_autoframe",
                            "animation_authoring",
                            "camera_inventory",
                            "camera_projection",
                            "camera_framing",
                            "mesh_diagnostics",
                            "skeleton_diagnostics",
                            "animation_inspection",
                            "animation_sampling",
                            "scene_transactions",
                            "scene_state",
                            "scene_save",
                            "task_queue",
                            "compilation_diagnostics",
                            "statement_code_execution",
                            "legacy_contract_parity",
                            "asset_management",
                            "asset_import",
                            "asset_inspection",
                            "asset_instantiation",
                            "humanoid_avatar_diagnostics",
                            "humanoid_avatar_configuration",
                            "humanoid_contact_constraints",
                            "inverse_kinematics",
                            "character_gaze",
                            "viewport_placement",
                            "animation_motion_qa",
                            "curve_discontinuity_detection",
                            "animation_transactions",
                            "effector_contact_baking",
                            "camera_subject_action",
                            "self_intersection_analysis"
                        }
                    });
                    responseJson = JsonUtility.ToJson(info);
                }
                else if ((method == "GET" || method == "POST") && path == "/api/editor/state")
                {
                    // Same main-thread requirement as /api/visora/info above - verified live, this
                    // was the very first call get_bridge_status's health check made, and it 500'd.
                    var state = await MainThreadDispatcher.EnqueueAsync(() =>
                    {
                        var scene = SceneManager.GetActiveScene();
                        return new EditorStateResponse
                        {
                            success = true,
                            isPlaying = EditorApplication.isPlaying,
                            isPaused = EditorApplication.isPaused,
                            isCompiling = EditorApplication.isCompiling,
                            activeSceneName = scene.name,
                            activeScenePath = scene.path,
                            isDirty = scene.isDirty
                        };
                    });
                    responseJson = JsonUtility.ToJson(state);
                }
                else if (method == "POST" && path == "/api/editor/play-mode")
                {
                    var body = ReadBody(req);
                    var payload = JsonUtility.FromJson<PlayModeRequest>(body);
                    bool enterPlay = payload != null && payload.action == "play";

                    await MainThreadDispatcher.EnqueueAsync(() =>
                    {
                        EditorApplication.isPlaying = enterPlay;
                    });

                    responseJson = JsonUtility.ToJson(new GenericSuccessResponse
                    {
                        success = true,
                        message = $"Play mode set to {enterPlay}"
                    });
                }
                else if (method == "POST" && path == "/api/editor/execute-code")
                {
                    var body = ReadBody(req);
                    var payload = JsonUtility.FromJson<ExecuteCodeRequest>(body);
                    if (payload == null || string.IsNullOrWhiteSpace(payload.code))
                    {
                        statusCode = 400;
                        responseJson = "{\"success\": false, \"error\": \"Request must include non-empty code\"}";
                    }
                    else
                    {
                        var result = await NativeCodeExecutionService.ExecuteAsync(payload.code, payload.timeoutSeconds);
                        responseJson = VisoraJson.Serialize(result);
                    }
                }
                else if (method == "POST" && path == "/api/scene/save")
                {
                    bool saved = await MainThreadDispatcher.EnqueueAsync(() =>
                    {
                        var scene = SceneManager.GetActiveScene();
                        return EditorSceneManager.SaveScene(scene);
                    });

                    responseJson = JsonUtility.ToJson(new GenericSuccessResponse
                    {
                        success = saved,
                        message = saved ? "Scene saved successfully" : "Failed to save scene"
                    });
                }
                else if (method == "GET" && path == "/api/compilation/errors")
                {
                    var status = CompilationService.GetCompilationStatus();
                    responseJson = JsonUtility.ToJson(status);
                }
                else if (method == "GET" && path == "/api/queue/status")
                {
                    string ticketId = req.QueryString["ticketId"];
                    var ticket = EditorTaskQueue.GetTicketStatus(ticketId);
                    if (ticket != null)
                    {
                        responseJson = JsonUtility.ToJson(ticket);
                    }
                    else
                    {
                        statusCode = 404;
                        responseJson = "{\"success\": false, \"error\": \"Ticket not found\"}";
                    }
                }
                else if (method == "POST" && path == "/api/queue/cancel")
                {
                    var body = ReadBody(req);
                    var payload = JsonUtility.FromJson<QueueCancelRequest>(body);
                    bool cancelled = payload != null && EditorTaskQueue.CancelTask(payload.ticketId);

                    responseJson = JsonUtility.ToJson(new GenericSuccessResponse
                    {
                        success = cancelled,
                        message = cancelled ? "Task cancelled" : "Task not found or already completed"
                    });
                }
                else if (method == "POST" && path == "/api/visora/camera/render")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CameraRenderRequest>(body) ?? new CameraRenderRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        CameraRenderingService.RenderCamera(p.cameraName, p.width, p.height, p.format));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/camera/sequence")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CameraSequenceRequest>(body) ?? new CameraSequenceRequest();

                    // Stepped, not EnqueueAsync: the capture has to span real editor time so game and
                    // animation state advance between frames. This request stays open for roughly
                    // frameCount * frameIntervalSeconds - clients must budget their timeout for it.
                    var sequence = new CameraSequenceResult();
                    await MainThreadDispatcher.EnqueueSteppedAsync(
                        () => CameraRenderingService.CaptureSequenceRoutine(
                            p.cameraName, p.width, p.height, p.frameCount, p.frameIntervalSeconds, sequence),
                        () => sequence);
                    responseJson = JsonUtility.ToJson(sequence);
                }
                else if (method == "POST" && path == "/api/visora/camera/diagnostic")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<DiagnosticCaptureRequest>(body) ?? new DiagnosticCaptureRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        DiagnosticCaptureService.Capture(p.subjectPath, p.width, p.height));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/camera/diagnostic-sequence")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<DiagnosticCaptureRequest>(body) ?? new DiagnosticCaptureRequest();

                    var sequence = new CameraSequenceResult();
                    await MainThreadDispatcher.EnqueueSteppedAsync(
                        () => DiagnosticCaptureService.CaptureSequenceRoutine(
                            p.subjectPath, p.width, p.height, p.frameCount, p.frameIntervalSeconds, sequence),
                        () => sequence);
                    responseJson = JsonUtility.ToJson(sequence);
                }
                else if (method == "POST" && path == "/api/visora/animation/preview-sequence")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AnimationPreviewRequest>(body) ?? new AnimationPreviewRequest();

                    var preview = new AnimationPreviewSequenceResult();
                    await MainThreadDispatcher.EnqueueSteppedAsync(
                        () => AnimationPreviewService.CapturePreviewRoutine(
                            p.cameraName, p.clipPath, p.targetObjectPath, p.width, p.height,
                            p.frameCount, p.fps, p.startTime, p.endTime, p.autoFrame, preview),
                        () => preview);
                    responseJson = JsonUtility.ToJson(preview);
                }
                else if (method == "POST" && path == "/api/visora/camera/list")
                {
                    var result = await MainThreadDispatcher.EnqueueAsync(CameraDiagnosticsService.ListCameras);
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/camera/project")
                {
                    var body = ReadBody(req);
                    var payload = JsonUtility.FromJson<CameraProjectRequest>(body) ?? new CameraProjectRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        CameraDiagnosticsService.ProjectWorldPoints(payload.cameraName, payload.points));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/camera/framing")
                {
                    var body = ReadBody(req);
                    var payload = JsonUtility.FromJson<CameraFramingRequest>(body) ?? new CameraFramingRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        CameraDiagnosticsService.DiagnoseFraming(payload.subjectPath, payload.cameraName));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/mesh/diagnose")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<MeshDiagnoseRequest>(body) ?? new MeshDiagnoseRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        MeshDiagnosticsService.Diagnose(p.targetName));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/skeleton/diagnose")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<SkeletonDiagnoseRequest>(body) ?? new SkeletonDiagnoseRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        SkeletonDiagnosticsService.Diagnose(p.rootObjectName, p.searchQuery));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/inspect")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AnimationInspectRequest>(body) ?? new AnimationInspectRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationInspectionService.InspectClip(p.clipName));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/sample")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AnimationSampleRequest>(body) ?? new AnimationSampleRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationInspectionService.SampleClip(p.clipName, p.targetObjectName, p.sampleTime));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/backups/list")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<ClipPathRequest>(body) ?? new ClipPathRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationBackupService.ListBackups(p.clipPath));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/backups/restore")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<RestoreClipRequest>(body) ?? new RestoreClipRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                    {
                        var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(p.clipPath);
                        if (clip == null)
                        {
                            return new RestoreAnimationClipResult
                            {
                                success = false,
                                clipPath = p.clipPath,
                                error = $"AnimationClip not found at '{p.clipPath}'."
                            };
                        }
                        return AnimationBackupService.RestoreBackup(clip, p.clipPath, p.backupId, p.operationId);
                    });
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/keyframes/list")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<KeyframeIdentityRequest>(body) ?? new KeyframeIdentityRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.ListKeyframes(p.clipPath, p.targetPath, p.typeName, p.propertyName));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/keyframes/set")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<SetKeyframeRequest>(body) ?? new SetKeyframeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.SetKeyframe(
                            p.clipPath, p.targetPath, p.typeName, p.propertyName,
                            p.time, p.values, p.tangentMode, p.inTangent, p.outTangent, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/keyframes/move")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<MoveKeyframeRequest>(body) ?? new MoveKeyframeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.MoveKeyframe(
                            p.clipPath, p.targetPath, p.typeName, p.propertyName,
                            p.fromTime, p.toTime, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/keyframes/remove")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<RemoveKeyframeRequest>(body) ?? new RemoveKeyframeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.RemoveKeyframe(
                            p.clipPath, p.targetPath, p.typeName, p.propertyName,
                            p.time, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/keyframes/hold")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<HoldKeyframeRequest>(body) ?? new HoldKeyframeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.SetKeyframeHold(
                            p.clipPath, p.targetPath, p.typeName, p.propertyName,
                            p.time, p.holdUntil, p.hasValue ? p.value : null, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/events/create")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CreateAnimationEventRequest>(body) ?? new CreateAnimationEventRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.CreateEvent(
                            p.clipPath, p.time, p.functionName, p.stringParam ?? "", p.floatParam, p.intParam, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/events/remove")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<RemoveAnimationEventRequest>(body) ?? new RemoveAnimationEventRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationAuthoringService.RemoveEvent(
                            p.clipPath, p.time, p.functionName, p.operationId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/transaction/begin")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<TransactionBeginRequest>(body) ?? new TransactionBeginRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        SceneTransactionService.BeginTransaction(p.description));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/transaction/commit")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<TransactionActionRequest>(body) ?? new TransactionActionRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        SceneTransactionService.CommitTransaction(p.transactionId, p.saveScene));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/transaction/rollback")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<TransactionActionRequest>(body) ?? new TransactionActionRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        SceneTransactionService.RollbackTransaction(p.transactionId));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "GET" && path == "/api/visora/asset/paths")
                {
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AssetManagementService.GetProjectPaths());
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/asset/import")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AssetImportRequest>(body) ?? new AssetImportRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AssetManagementService.ImportAsset(p.assetPath, p.allowUnityPackage));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/asset/inspect")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AssetInspectRequest>(body) ?? new AssetInspectRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AssetManagementService.InspectAsset(p.assetPath));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/asset/instantiate")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AssetInstantiateRequest>(body) ?? new AssetInstantiateRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AssetManagementService.InstantiateAsset(p.assetPath, p.parentPath, p.position, p.rotation, p.scale, p.name));
                    responseJson = JsonUtility.ToJson(result);
                }
                else if (method == "POST" && path == "/api/visora/humanoid/validate")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<HumanoidValidateRequest>(body) ?? new HumanoidValidateRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        HumanoidService.ValidateAvatar(p.targetPath, p.assetPath));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/humanoid/configure")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<HumanoidConfigureRequest>(body) ?? new HumanoidConfigureRequest();
                    Dictionary<string, string> overrides = null;
                    if (p.boneOverrideKeys != null && p.boneOverrideValues != null &&
                        p.boneOverrideKeys.Length == p.boneOverrideValues.Length)
                    {
                        overrides = new Dictionary<string, string>(StringComparer.Ordinal);
                        for (int i = 0; i < p.boneOverrideKeys.Length; i++)
                        {
                            overrides[p.boneOverrideKeys[i]] = p.boneOverrideValues[i];
                        }
                    }
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        HumanoidService.ConfigureHumanoid(p.assetPath, overrides, p.sourceAvatarPath));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/humanoid/contact/analyze")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<ContactAnalyzeRequest>(body) ?? new ContactAnalyzeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        HumanoidContactService.AnalyzeContacts(
                            p.targetPath, p.clipPath, p.effectors, p.groundMode,
                            p.groundY, p.velThreshold, p.heightTol));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/humanoid/contact/bake")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<ContactBakeRequest>(body) ?? new ContactBakeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        HumanoidContactService.BakeContacts(
                            p.targetPath, p.clipPath, p.outputClipPath, p.effectors,
                            p.groundY, p.fixSliding, p.fixPenetration, p.operationId));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/ik/two-bone")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<TwoBoneIKRequest>(body) ?? new TwoBoneIKRequest();
                    float? st = p.hasSampleTime ? (float?)p.sampleTime : null;
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        InverseKinematicsService.SolveTwoBoneIK(
                            p.targetPath, p.effector, p.rootBone, p.midBone, p.endBone,
                            p.targetPosition, p.targetRotation, p.poleVector,
                            p.space, p.cameraName, p.weight, p.applyToScene, p.bakeToClip, st));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/viewport-placement")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<ViewportPlacementRequest>(body) ?? new ViewportPlacementRequest();
                    float? st = p.hasSampleTime ? (float?)p.sampleTime : null;
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        InverseKinematicsService.PlaceEffectorInViewport(
                            p.cameraName, p.targetPath, p.effector, p.rootBone, p.midBone, p.endBone,
                            p.viewportX, p.viewportY, p.cameraDepth, p.alignMode,
                            p.customRotation, p.poleVector, p.weight, p.applyToScene, p.bakeToClip, st));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/gaze/solve")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CharacterGazeRequest>(body) ?? new CharacterGazeRequest();
                    float? st = p.hasSampleTime ? (float?)p.sampleTime : null;
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        GazeService.SolveCharacterGaze(
                            p.targetPath, p.targetLookAtPosition, p.targetTransformPath,
                            p.chestWeight, p.neckWeight, p.headWeight, p.eyesWeight,
                            p.upVector, p.applyToScene, p.bakeToClip, st));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/qa/motion")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<MotionQARequest>(body) ?? new MotionQARequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationMotionQAService.AnalyzeJointMotion(
                            p.clipPath, p.targetPath, p.bones, p.sampleFps,
                            p.jerkThreshold, p.angularJerkThreshold));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/qa/discontinuities")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CurveDiscontinuityRequest>(body) ?? new CurveDiscontinuityRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationMotionQAService.DetectCurveDiscontinuities(
                            p.clipPath, p.filterCurves, p.autoFix));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/transaction/execute")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<AnimationTransactionRequest>(body) ?? new AnimationTransactionRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationTransactionService.ExecuteTransaction(p));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/contact/bake-effector")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<EffectorContactBakeRequest>(body) ?? new EffectorContactBakeRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationEffectorContactService.BakeContact(p));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/action/camera-subject-contact")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<CameraSubjectContactRequest>(body) ?? new CameraSubjectContactRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        CameraSubjectActionService.SolveCameraSubjectContact(p));
                    responseJson = VisoraJson.Serialize(result);
                }
                else if (method == "POST" && path == "/api/visora/animation/intersections/analyze")
                {
                    var body = ReadBody(req);
                    var p = JsonUtility.FromJson<SelfIntersectionRequest>(body) ?? new SelfIntersectionRequest();
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        AnimationSelfIntersectionService.AnalyzeSelfIntersections(p));
                    responseJson = VisoraJson.Serialize(result);
                }
                else
                {
                    statusCode = 404;
                    responseJson = "{\"success\": false, \"error\": \"Endpoint not found\"}";
                }

                byte[] buffer = Encoding.UTF8.GetBytes(responseJson);
                res.StatusCode = statusCode;
                res.ContentType = "application/json";
                res.ContentLength64 = buffer.Length;
                await res.OutputStream.WriteAsync(buffer, 0, buffer.Length);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[Visora] Router error processing {path}: {ex}");
                byte[] errBuffer = Encoding.UTF8.GetBytes($"{{\"success\": false, \"error\": \"Internal server error: {ex.Message}\"}}");
                res.StatusCode = 500;
                res.ContentType = "application/json";
                res.ContentLength64 = errBuffer.Length;
                await res.OutputStream.WriteAsync(errBuffer, 0, errBuffer.Length);
            }
            finally
            {
                res.Close();
            }
        }

        private static string ReadBody(HttpListenerRequest req)
        {
            if (!req.HasEntityBody) return "{}";
            using (var reader = new System.IO.StreamReader(req.InputStream, req.ContentEncoding))
            {
                return reader.ReadToEnd();
            }
        }
    }

    [Serializable]
    public class PingResponse
    {
        public bool success;
        public string message;
        public string version;
        public string flavor;
        public string unityVersion;
    }

    [Serializable]
    public class BridgeInfoResponse
    {
        public bool success;
        public string flavor;
        public string version;
        public int apiVersion;
        public string unityVersion;
        public bool isPlaying;
        public bool isCompiling;
        public string activeScene;
        public List<string> supportedFeatures = new List<string>();
    }

    [Serializable]
    public class EditorStateResponse
    {
        public bool success;
        public bool isPlaying;
        public bool isPaused;
        public bool isCompiling;
        public string activeSceneName;
        public string activeScenePath;
        public bool isDirty;
    }

    [Serializable]
    public class GenericSuccessResponse
    {
        public bool success;
        public string message;
    }
}
