using System;
using System.Collections.Generic;
using UnityEngine;

namespace Visora.Editor.Services
{
    /// <summary>Typed camera inventory, projection, and framing diagnostics for the native protocol.</summary>
    internal static class CameraDiagnosticsService
    {
        public static Dictionary<string, object> ListCameras()
        {
            var cameras = UnityEngine.Object.FindObjectsOfType<Camera>();
            var items = new List<object>();
            foreach (var camera in cameras)
            {
                items.Add(new Dictionary<string, object>
                {
                    { "name", camera.name }, { "path", HierarchyPath(camera.transform) },
                    { "enabled", camera.enabled }, { "active", camera.gameObject.activeInHierarchy },
                    { "tag", camera.tag }, { "depth", camera.depth }, { "fieldOfView", camera.fieldOfView },
                    { "orthographic", camera.orthographic }, { "orthographicSize", camera.orthographicSize }
                });
            }
            return new Dictionary<string, object> { { "success", true }, { "cameras", items } };
        }

        public static Dictionary<string, object> ProjectWorldPoints(string cameraName, float[] points)
        {
            var camera = CameraRenderingService.FindCamera(cameraName);
            if (camera == null) return Failure($"Camera not found: {cameraName}");
            var flat = points ?? Array.Empty<float>();
            if (flat.Length % 3 != 0) return Failure("points must be a flat list of x,y,z triples (length a multiple of three).");
            var projected = new List<object>();
            for (var i = 0; i < flat.Length; i += 3)
            {
                var viewport = camera.WorldToViewportPoint(new Vector3(flat[i], flat[i + 1], flat[i + 2]));
                projected.Add(new Dictionary<string, object>
                {
                    { "x", viewport.x }, { "y", viewport.y }, { "z", viewport.z }, { "isBehindCamera", viewport.z < 0f }
                });
            }
            return new Dictionary<string, object> { { "success", true }, { "screenPoints", projected } };
        }

        public static Dictionary<string, object> DiagnoseFraming(string subjectPath, string cameraName)
        {
            var camera = CameraRenderingService.FindCamera(cameraName);
            if (camera == null) return Failure($"Camera not found: {cameraName}");
            var subject = GameObject.Find(subjectPath);
            if (subject == null) return Failure($"Subject not found: {subjectPath}");
            var renderers = subject.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0) return Failure($"Subject '{subjectPath}' has no renderers.");

            var bounds = renderers[0].bounds;
            for (var index = 1; index < renderers.Length; index++) bounds.Encapsulate(renderers[index].bounds);
            var min = new Vector3(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity);
            var max = new Vector3(float.NegativeInfinity, float.NegativeInfinity, float.NegativeInfinity);
            var visible = 0;
            var behind = 0;
            foreach (var corner in Corners(bounds))
            {
                var viewport = camera.WorldToViewportPoint(corner);
                min = Vector3.Min(min, viewport);
                max = Vector3.Max(max, viewport);
                if (viewport.z < 0f) behind++;
                if (viewport.z >= 0f && viewport.x >= 0f && viewport.x <= 1f && viewport.y >= 0f && viewport.y <= 1f) visible++;
            }
            var visibleRatio = visible / 8f;
            var isBehind = behind == 8;
            var clipped = !isBehind && (min.x < 0f || min.y < 0f || max.x > 1f || max.y > 1f);
            var status = isBehind ? "behind_camera" : visibleRatio <= 0f ? "off_screen" : clipped ? "clipped" : "visible";
            return new Dictionary<string, object>
            {
                { "success", true }, { "subjectPath", subjectPath }, { "cameraName", camera.name },
                { "viewportBounds", new[] { min.x, min.y, max.x, max.y } }, { "visibleRatio", visibleRatio },
                { "isVisible", visible > 0 }, { "isBehindCamera", isBehind }, { "isClipped", clipped }, { "framingStatus", status }
            };
        }

        private static IEnumerable<Vector3> Corners(Bounds bounds)
        {
            var min = bounds.min;
            var max = bounds.max;
            yield return new Vector3(min.x, min.y, min.z); yield return new Vector3(min.x, min.y, max.z);
            yield return new Vector3(min.x, max.y, min.z); yield return new Vector3(min.x, max.y, max.z);
            yield return new Vector3(max.x, min.y, min.z); yield return new Vector3(max.x, min.y, max.z);
            yield return new Vector3(max.x, max.y, min.z); yield return new Vector3(max.x, max.y, max.z);
        }

        private static Dictionary<string, object> Failure(string error)
        {
            return new Dictionary<string, object> { { "success", false }, { "error", error } };
        }

        private static string HierarchyPath(Transform transform)
        {
            var names = new List<string>();
            while (transform != null) { names.Insert(0, transform.name); transform = transform.parent; }
            return string.Join("/", names);
        }
    }
}
