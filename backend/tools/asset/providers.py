"""
Asset search providers for discovering 3D models, textures, and materials.
Includes ambientCG (zero-config, CC0), Sketchfab, Poly Pizza, and Direct URL handlers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.config import get_settings
from backend.schemas.asset import AssetSearchResultItem
from backend.tools.asset.downloader import extract_filename_from_url

logger = logging.getLogger("backend.tools.asset.providers")


class BaseAssetProvider(ABC):
    """Abstract base class for 3D asset providers."""

    name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 10,
    ) -> tuple[list[AssetSearchResultItem], list[str]]:
        """Searches the provider for assets matching query and category."""
        ...

    @abstractmethod
    async def resolve_download_url(
        self,
        asset_id_or_url: str,
    ) -> tuple[str | None, list[str]]:
        """Resolves a direct downloadable file URL for an asset."""
        ...


class AmbientCGProvider(BaseAssetProvider):
    """Provider for ambientCG CC0 textures, materials, HDRI, and 3D models. No API key required."""

    name = "ambientcg"
    BASE_URL = "https://ambientcg.com/api/v2"

    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 10,
    ) -> tuple[list[AssetSearchResultItem], list[str]]:
        items: list[AssetSearchResultItem] = []
        warnings: list[str] = []
        settings = get_settings()

        params: dict[str, Any] = {
            "q": query,
            "limit": min(max(1, limit), 50),
            "include": "downloadData",
        }

        # Filter by category if requested.
        # ambientCG's `type` param silently no-ops on an unrecognized value (it falls back to
        # the unfiltered result set instead of erroring or returning empty), so a wrong string
        # here looks exactly like "nothing matched" instead of "the filter never applied".
        # Verified against the live API: it wants lowercase, hyphenated "3d-model" for models -
        # "3DModel"/"Model" both silently no-op. "material"/"hdri" happen to work in either case
        # but are normalized here too for consistency with the confirmed-working value.
        cat_lower = category.lower()
        if cat_lower in {"model", "3d", "mesh"}:
            params["type"] = "3d-model"
        elif cat_lower in {"texture", "material", "pbr"}:
            params["type"] = "material"
        elif cat_lower in {"hdri", "environment", "sky"}:
            params["type"] = "hdri"

        try:
            async with httpx.AsyncClient(timeout=settings.unity_bridge_timeout_seconds) as client:
                res = await client.get(f"{self.BASE_URL}/full_json", params=params)
                res.raise_for_status()
                data = res.json()

            found_assets = data.get("foundAssets", [])
            for asset in found_assets:
                asset_id = asset.get("assetId", "")
                data_type = asset.get("dataType", "Material")
                display_name = asset.get("displayName") or asset_id
                tags = asset.get("tags", [])

                # Map data type to Visora category
                visora_cat = "material"
                if data_type == "3DModel":
                    visora_cat = "model"
                elif data_type == "HDRI":
                    visora_cat = "environment"

                # Find preview thumbnail
                preview_images = asset.get("previewImage", {})
                thumbnail_url = (
                    preview_images.get("256-PNG")
                    or preview_images.get("256-JPG-FFFFFF")
                    or preview_images.get("512-PNG")
                    or preview_images.get("128-PNG")
                )

                # Extract download links and formats
                formats: list[str] = []
                download_url: str | None = None
                download_folders = asset.get("downloadFolders", {})
                default_downloads = download_folders.get("default", {}).get("downloadFiletypeCategories", {})

                for ftype, details in default_downloads.items():
                    formats.append(ftype)
                    downloads = details.get("downloads", [])
                    # Pick 1K or 2K zip preferentially for agent speed
                    for d in downloads:
                        attr = d.get("attribute", "")
                        if "1K" in attr or "2K" in attr:
                            download_url = d.get("downloadLink") or d.get("fullDownloadPath")
                            break
                    if not download_url and downloads:
                        download_url = downloads[0].get("downloadLink") or downloads[0].get("fullDownloadPath")

                # Fallback download link
                if not download_url:
                    download_url = f"https://ambientcg.com/get?file={asset_id}_1K-PNG.zip"
                    formats.append("zip")

                items.append(
                    AssetSearchResultItem(
                        id=f"ambientcg:{asset_id}",
                        name=display_name,
                        source="ambientcg",
                        category=visora_cat,
                        description=f"{data_type} asset from ambientCG. Tags: {', '.join(tags[:6])}",
                        thumbnail_url=thumbnail_url,
                        author="ambientCG / Lennart Demes",
                        license="CC0 (Public Domain)",
                        file_formats=formats or ["zip"],
                        download_url=download_url,
                        details={
                            "asset_id": asset_id,
                            "data_type": data_type,
                            "tags": tags[:10],
                            "popularity": asset.get("popularityScore", 0),
                        },
                    )
                )
        except Exception as exc:
            logger.warning(f"ambientCG search error: {exc}")
            warnings.append(f"ambientCG search failed: {exc}")

        return items, warnings

    async def resolve_download_url(
        self,
        asset_id_or_url: str,
    ) -> tuple[str | None, list[str]]:
        if asset_id_or_url.startswith("http"):
            return asset_id_or_url, []
        raw_id = asset_id_or_url.replace("ambientcg:", "").strip()
        # ambientCG's download filename format differs by asset type: materials/HDRIs use
        # "<id>_<resolution>-<format>.zip" (e.g. Bricks097_1K-PNG.zip), but 3D model assets add
        # an extra quality tier: "<id>_<quality>-<resolution>-<format>.zip" (e.g.
        # 3DApple002_LQ-1K-PNG.zip). Guessing the material pattern for a model 404s every time -
        # verified live by downloading real 3D-model assets. There's no reliable API round-trip
        # to look up a single asset by id (assetId/forceSpecificAssetId both silently no-op), but
        # every 3D model assetId in ambientCG's current catalog is "3D"-prefixed, so use that as
        # a cheap signal instead.
        if raw_id.startswith("3D"):
            return f"https://ambientcg.com/get?file={raw_id}_LQ-1K-PNG.zip", []
        return f"https://ambientcg.com/get?file={raw_id}_1K-PNG.zip", []


class SketchfabProvider(BaseAssetProvider):
    """Provider for Sketchfab 3D models. Public search works without API key; download uses SKETCHFAB_API_TOKEN."""

    name = "sketchfab"
    BASE_URL = "https://api.sketchfab.com/v3"

    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 10,
    ) -> tuple[list[AssetSearchResultItem], list[str]]:
        _ = category
        items: list[AssetSearchResultItem] = []
        warnings: list[str] = []
        settings = get_settings()

        params: dict[str, Any] = {
            "q": query,
            "type": "models",
            "downloadable": "true",
            "count": min(max(1, limit), 24),
        }

        headers: dict[str, str] = {}
        if settings.sketchfab_api_token:
            headers["Authorization"] = f"Token {settings.sketchfab_api_token}"

        try:
            async with httpx.AsyncClient(timeout=settings.unity_bridge_timeout_seconds) as client:
                res = await client.get(f"{self.BASE_URL}/models", params=params, headers=headers)
                res.raise_for_status()
                data = res.json()

            results = data.get("results", [])
            for model in results:
                uid = model.get("uid", "")
                name = model.get("name", "Untitled")
                user = model.get("user", {})
                author = user.get("displayName") or user.get("username", "Unknown")
                license_info = model.get("license", {})
                license_label = license_info.get("label") or license_info.get("slug", "Standard")

                # Thumbnail image
                thumbnails = model.get("thumbnails", {}).get("images", [])
                thumbnail_url = thumbnails[0].get("url") if thumbnails else None

                vertex_count = model.get("vertexCount", 0)
                face_count = model.get("faceCount", 0)
                animation_count = model.get("animationCount", 0)

                items.append(
                    AssetSearchResultItem(
                        id=f"sketchfab:{uid}",
                        name=name,
                        source="sketchfab",
                        category="model",
                        description=f"Sketchfab 3D model by {author}. Polygons: {face_count:,}, Animations: {animation_count}",
                        thumbnail_url=thumbnail_url,
                        author=author,
                        license=license_label,
                        file_formats=["gltf", "glb", "usdz"],
                        download_url=None,  # Requires token resolution via /models/{uid}/download
                        details={
                            "uid": uid,
                            "vertex_count": vertex_count,
                            "face_count": face_count,
                            "animation_count": animation_count,
                            "viewer_url": model.get("viewerUrl"),
                        },
                    )
                )
        except Exception as exc:
            logger.warning(f"Sketchfab search error: {exc}")
            warnings.append(f"Sketchfab search failed: {exc}")

        return items, warnings

    async def resolve_download_url(
        self,
        asset_id_or_url: str,
    ) -> tuple[str | None, list[str]]:
        if asset_id_or_url.startswith("http"):
            return asset_id_or_url, []

        settings = get_settings()
        if not settings.sketchfab_api_token:
            return None, ["Sketchfab direct download requires SKETCHFAB_API_TOKEN in environment/config."]

        uid = asset_id_or_url.replace("sketchfab:", "").strip()
        headers = {"Authorization": f"Token {settings.sketchfab_api_token}"}
        try:
            async with httpx.AsyncClient(timeout=settings.unity_bridge_timeout_seconds) as client:
                res = await client.get(f"{self.BASE_URL}/models/{uid}/download", headers=headers)
                res.raise_for_status()
                data = res.json()
                gltf = data.get("gltf", {})
                download_url = gltf.get("url")
                if download_url:
                    return download_url, []
                return None, ["No glTF download link returned by Sketchfab API."]
        except Exception as exc:
            return None, [f"Failed to resolve Sketchfab download URL: {exc}"]


class PolyPizzaProvider(BaseAssetProvider):
    """Provider for Poly Pizza CC0 low-poly 3D models. Requires POLY_PIZZA_API_KEY."""

    name = "polypizza"
    BASE_URL = "https://api.poly.pizza/v1"

    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 10,
    ) -> tuple[list[AssetSearchResultItem], list[str]]:
        _ = category
        items: list[AssetSearchResultItem] = []
        warnings: list[str] = []
        settings = get_settings()

        if not settings.poly_pizza_api_key:
            warnings.append("Poly Pizza requires POLY_PIZZA_API_KEY; skipped or configure key to enable.")
            return items, warnings

        headers = {"x-auth-token": settings.poly_pizza_api_key}
        params: dict[str, str | int] = {"query": query, "limit": min(max(1, limit), 30)}

        try:
            async with httpx.AsyncClient(timeout=settings.unity_bridge_timeout_seconds) as client:
                res = await client.get(f"{self.BASE_URL}/search", params=params, headers=headers)
                res.raise_for_status()
                data = res.json()

            results = data.get("results", []) if isinstance(data, dict) else []
            for model in results:
                mid = model.get("id") or model.get("_id", "")
                name = model.get("Title") or model.get("name", "Untitled")
                author = model.get("Creator") or model.get("author", "Poly Pizza")
                download_url = model.get("Download") or model.get("downloadUrl")
                thumbnail_url = model.get("Thumbnail") or model.get("thumbnail")

                items.append(
                    AssetSearchResultItem(
                        id=f"polypizza:{mid}",
                        name=name,
                        source="polypizza",
                        category="model",
                        description=f"Poly Pizza low-poly 3D asset by {author}",
                        thumbnail_url=thumbnail_url,
                        author=author,
                        license="CC0 (Public Domain)",
                        file_formats=["glb", "obj"],
                        download_url=download_url,
                        details={"id": mid, "triangles": model.get("TriCount", 0)},
                    )
                )
        except Exception as exc:
            logger.warning(f"Poly Pizza search error: {exc}")
            warnings.append(f"Poly Pizza search failed: {exc}")

        return items, warnings

    async def resolve_download_url(
        self,
        asset_id_or_url: str,
    ) -> tuple[str | None, list[str]]:
        if asset_id_or_url.startswith("http"):
            return asset_id_or_url, []
        return None, ["Poly Pizza download URLs must be resolved from search results."]


class DirectUrlProvider(BaseAssetProvider):
    """Direct URL provider for user-supplied asset links."""

    name = "direct"

    async def search(
        self,
        query: str,
        category: str = "all",
        limit: int = 10,
    ) -> tuple[list[AssetSearchResultItem], list[str]]:
        _ = (category, limit)
        if not (query.startswith("http://") or query.startswith("https://")):
            return [], []

        url = query.strip()
        # Reuse the downloader's filename resolution instead of a naive path split: URLs like
        # ambientCG's own "https://ambientcg.com/get?file=Rock030_1K-PNG.zip" carry the real
        # filename in a query param. A plain split-on-"?" mislabeled every one of them (id/name
        # came back as just "get", category as "model" for what is really a texture zip) even
        # though the download itself worked fine because download_url kept the full URL.
        filename = extract_filename_from_url(url)
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        cat = "model"
        if ext in {"png", "jpg", "jpeg", "tga", "exr"}:
            cat = "texture"
        elif ext in {"unitypackage"}:
            cat = "package"

        item = AssetSearchResultItem(
            id=f"direct:{filename or 'asset'}",
            name=filename or "Direct Web Asset",
            source="direct",
            category=cat,
            description=f"Directly supplied web asset URL ({ext.upper() if ext else 'raw file'})",
            thumbnail_url=None,
            author="Web Link",
            license="User Provided",
            file_formats=[ext] if ext else ["raw"],
            download_url=url,
            details={"url": url, "filename": filename},
        )
        return [item], []

    async def resolve_download_url(
        self,
        asset_id_or_url: str,
    ) -> tuple[str | None, list[str]]:
        if asset_id_or_url.startswith("http://") or asset_id_or_url.startswith("https://"):
            return asset_id_or_url, []
        return None, ["Invalid direct web URL."]
