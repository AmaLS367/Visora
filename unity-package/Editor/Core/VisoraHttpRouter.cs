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
                        version = "1.1.0",
                        flavor = "visora-native",
                        unityVersion = Application.unityVersion
                    });
                }
                else if (method == "GET" && path == "/api/visora/info")
                {
                    responseJson = JsonUtility.ToJson(new BridgeInfoResponse
                    {
                        success = true,
                        flavor = "visora-native",
                        version = "1.1.0",
                        apiVersion = 2,
                        unityVersion = Application.unityVersion,
                        isPlaying = EditorApplication.isPlaying,
                        isCompiling = EditorApplication.isCompiling,
                        activeScene = SceneManager.GetActiveScene().name,
                        supportedFeatures = new List<string>
                        {
                            "camera_render",
                            "camera_sequence",
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
                            "asset_instantiation"
                        }
                    });
                }
                else if (method == "POST" && path == "/api/editor/state")
                {
                    var scene = SceneManager.GetActiveScene();
                    responseJson = JsonUtility.ToJson(new EditorStateResponse
                    {
                        success = true,
                        isPlaying = EditorApplication.isPlaying,
                        isPaused = EditorApplication.isPaused,
                        isCompiling = EditorApplication.isCompiling,
                        activeSceneName = scene.name,
                        activeScenePath = scene.path,
                        isDirty = scene.isDirty
                    });
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
                    var result = await MainThreadDispatcher.EnqueueAsync(() =>
                        CameraRenderingService.CaptureSequence(p.cameraName, p.width, p.height, p.frameCount, p.frameIntervalSeconds));
                    responseJson = JsonUtility.ToJson(result);
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
