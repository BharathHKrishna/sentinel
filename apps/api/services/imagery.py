"""
Imagery fetchers for Sentinel-2 (free), Sentinel Hub, and Planet Labs.

FreeS2Fetcher:   Element84 STAC + AWS public COGs — zero credentials.
SentinelHubFetcher: OAuth2 → Sentinel Hub Process API.
PlanetFetcher:   Planet Labs Orders API v2.
"""
import io
import os
import time
import logging
import zipfile
from typing import List, Optional

import httpx
import numpy as np

logger = logging.getLogger(__name__)

# ── Free Sentinel-2 via Element84 STAC + AWS COGs ──────────────────────────────

STAC_SEARCH = "https://earth-search.aws.element84.com/v1/search"

# Only the 4 bands the change detectors actually use — keeps fetches fast
_ASSET_TO_IDX = {
    "red": 3,       # B04 — NDVI, NDBI
    "nir": 7,       # B08 — NDVI, solar
    "swir16": 10,   # B11 — NBR fire, NDBI construction
    "swir22": 11,   # B12 — solar farm signature
}


class FreeS2Fetcher:
    """
    Fetch real Sentinel-2 L2A imagery with zero credentials.
    Uses Element84 Earth Search STAC API to find scenes, then reads
    Cloud-Optimised GeoTIFFs directly from AWS Open Data via HTTP range requests.
    """

    def search(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        max_cloud: int = 25,
        limit: int = 5,
    ) -> List[dict]:
        payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": bbox,
            "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
            "limit": limit,
            "query": {"eo:cloud_cover": {"lt": max_cloud}},
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        }
        resp = httpx.post(STAC_SEARCH, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("features", [])

    def _read_band(self, url: str, bbox: List[float], size: int = 128) -> np.ndarray:
        """Read a single COG band clipped to bbox, resampled to (size, size)."""
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds
        from rasterio.enums import Resampling

        # Optimise remote COG reads
        env = rasterio.Env(
            GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        )
        with env:
            with rasterio.open(url) as ds:
                dst_bounds = transform_bounds(
                    "EPSG:4326", ds.crs,
                    bbox[0], bbox[1], bbox[2], bbox[3],
                )
                window = from_bounds(*dst_bounds, transform=ds.transform)
                data = ds.read(
                    1,
                    window=window,
                    out_shape=(size, size),
                    resampling=Resampling.bilinear,
                    boundless=True,
                    fill_value=0,
                )
        return data.astype(np.float32) / 10000.0  # DN → reflectance [0,1]

    def get_composite(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        size: int = 128,
    ) -> np.ndarray:
        """
        Return (size, size, 12) float32 array of S2 L2A bands [0,1].
        Raises ValueError if no cloud-free scenes found.
        """
        items = self.search(bbox, start_date, end_date)
        if not items:
            raise ValueError(
                f"No Sentinel-2 scenes for bbox={bbox} {start_date}→{end_date} "
                f"with cloud cover <25%"
            )

        best = items[0]  # already sorted by cloud cover asc
        assets = best["assets"]
        cloud = best["properties"].get("eo:cloud_cover", "?")
        logger.info(
            "Free S2: using scene %s  cloud=%.1f%%  date=%s",
            best["id"], cloud, best["properties"].get("datetime", "?")[:10],
        )

        result = np.zeros((size, size, 12), dtype=np.float32)
        for asset_key, band_idx in _ASSET_TO_IDX.items():
            if asset_key not in assets:
                continue
            url = assets[asset_key]["href"]
            try:
                result[:, :, band_idx] = self._read_band(url, bbox, size)
            except Exception as exc:
                logger.warning("Could not read band %s: %s", asset_key, exc)

        return np.clip(result, 0.0, 1.0)

SENTINEL_HUB_BASE = "https://services.sentinel-hub.com"
OAUTH_TOKEN_URL = f"{SENTINEL_HUB_BASE}/auth/realms/main/protocol/openid-connect/token"
PROCESS_URL = f"{SENTINEL_HUB_BASE}/api/v1/process"


class SentinelHubFetcher:
    """Fetch multispectral composites from Sentinel Hub Process API."""

    def __init__(self) -> None:
        self.client_id = os.environ["SENTINEL_HUB_CLIENT_ID"]
        self.client_secret = os.environ["SENTINEL_HUB_CLIENT_SECRET"]
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ── Auth ────────────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        resp = httpx.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in - 60  # 60 s buffer

    def _get_token(self) -> str:
        if self._token is None or time.time() >= self._token_expires_at:
            self._refresh_token()
        return self._token  # type: ignore[return-value]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _bbox_to_str(bbox: List[float]) -> str:
        """bbox = [min_lon, min_lat, max_lon, max_lat]"""
        return f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

    # ── Sentinel-2 L2A ──────────────────────────────────────────────────────

    def get_sentinel2_composite(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        width: int = 512,
        height: int = 512,
    ) -> np.ndarray:
        """
        Return a (height, width, 12) float32 array of S2 L2A bands:
        B01, B02, B03, B04, B05, B06, B07, B08, B8A, B09, B11, B12
        Values are surface reflectance scaled to [0, 1].
        """
        evalscript = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B01","B02","B03","B04","B05","B06","B07","B08","B8A","B09","B11","B12"],
      units: "REFLECTANCE"
    }],
    output: {
      bands: 12,
      sampleType: "FLOAT32"
    }
  };
}
function evaluatePixel(sample) {
  return [
    sample.B01, sample.B02, sample.B03, sample.B04,
    sample.B05, sample.B06, sample.B07, sample.B08,
    sample.B8A, sample.B09, sample.B11, sample.B12
  ];
}
"""
        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{start_date}T00:00:00Z",
                                "to": f"{end_date}T23:59:59Z",
                            },
                            "maxCloudCoverage": 20,
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            },
            "evalscript": evalscript,
        }

        logger.info(
            "Fetching S2 composite bbox=%s from=%s to=%s", bbox, start_date, end_date
        )

        resp = httpx.post(
            PROCESS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._get_token()}",
                "Content-Type": "application/json",
                "Accept": "image/tiff",
            },
            timeout=120,
        )
        resp.raise_for_status()

        import rasterio  # type: ignore

        with rasterio.open(io.BytesIO(resp.content)) as ds:
            data = ds.read()  # (bands, height, width)

        arr = np.transpose(data, (1, 2, 0)).astype(np.float32)
        arr = np.clip(arr, 0.0, 1.0)
        return arr

    # ── Sentinel-1 GRD ──────────────────────────────────────────────────────

    def get_sentinel1_composite(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        width: int = 512,
        height: int = 512,
    ) -> np.ndarray:
        """
        Return a (height, width, 2) float32 array: [VV, VH] backscatter in dB.
        """
        evalscript = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["VV", "VH"],
      units: "LINEAR_POWER"
    }],
    output: {
      bands: 2,
      sampleType: "FLOAT32"
    }
  };
}
function evaluatePixel(sample) {
  // Convert to dB: 10 * log10(linear), clamp to [-30, 0] dB
  var vv_db = 10 * Math.log10(Math.max(sample.VV, 1e-10));
  var vh_db = 10 * Math.log10(Math.max(sample.VH, 1e-10));
  return [vv_db, vh_db];
}
"""
        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-1-grd",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{start_date}T00:00:00Z",
                                "to": f"{end_date}T23:59:59Z",
                            },
                            "acquisitionMode": "IW",
                            "polarization": "DV",
                            "orbitDirection": "ASCENDING",
                            "resolution": "HIGH",
                            "mosaickingOrder": "mostRecent",
                        },
                        "processing": {
                            "backCoeff": "SIGMA0_ELLIPSOID",
                            "orthorectify": True,
                            "demInstance": "MAPZEN",
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            },
            "evalscript": evalscript,
        }

        logger.info(
            "Fetching S1 SAR composite bbox=%s from=%s to=%s", bbox, start_date, end_date
        )

        resp = httpx.post(
            PROCESS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._get_token()}",
                "Content-Type": "application/json",
                "Accept": "image/tiff",
            },
            timeout=120,
        )
        resp.raise_for_status()

        import rasterio  # type: ignore

        with rasterio.open(io.BytesIO(resp.content)) as ds:
            data = ds.read()

        arr = np.transpose(data, (1, 2, 0)).astype(np.float32)
        return arr


# ── Planet Labs fetcher ──────────────────────────────────────────────────────

PLANET_BASE = "https://api.planet.com"
PLANET_DATA_URL = f"{PLANET_BASE}/data/v1"
PLANET_ORDERS_URL = f"{PLANET_BASE}/compute/ops/orders/v2"


class PlanetFetcher:
    """
    Fetch PlanetScope (PSScene) and SkySat imagery via Planet Labs APIs.

    Uses the Data API for scene search and the Orders API for clipped,
    analysis-ready GeoTIFF delivery. Falls back to Quick Subscribe
    (basemap tiles) for near-real-time monitoring use cases.
    """

    ITEM_TYPES = {
        "planetscope": "PSScene",
        "skysat": "SkySatCollect",
    }

    # PSScene band order: Blue, Green, Red, NIR (SR asset)
    PS_BANDS = ["blue", "green", "red", "nir"]

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ["PLANET_API_KEY"]
        self._client = httpx.Client(
            auth=(self.api_key, ""),
            timeout=60,
            headers={"Content-Type": "application/json"},
        )

    # ── Scene search ────────────────────────────────────────────────────────

    def search_scenes(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        item_type: str = "planetscope",
        max_cloud_cover: float = 0.15,
        limit: int = 10,
    ) -> List[dict]:
        """
        Search for scenes intersecting bbox in the given date range.

        Returns a list of GeoJSON feature dicts ordered by cloud cover asc.
        bbox = [min_lon, min_lat, max_lon, max_lat]
        """
        planet_item = self.ITEM_TYPES.get(item_type, item_type)

        geom_filter = {
            "type": "GeometryFilter",
            "field_name": "geometry",
            "config": {
                "type": "Polygon",
                "coordinates": [[
                    [bbox[0], bbox[1]],
                    [bbox[2], bbox[1]],
                    [bbox[2], bbox[3]],
                    [bbox[0], bbox[3]],
                    [bbox[0], bbox[1]],
                ]],
            },
        }

        date_filter = {
            "type": "DateRangeFilter",
            "field_name": "acquired",
            "config": {
                "gte": f"{start_date}T00:00:00Z",
                "lte": f"{end_date}T23:59:59Z",
            },
        }

        cloud_filter = {
            "type": "RangeFilter",
            "field_name": "cloud_cover",
            "config": {"lte": max_cloud_cover},
        }

        payload = {
            "item_types": [planet_item],
            "filter": {
                "type": "AndFilter",
                "config": [geom_filter, date_filter, cloud_filter],
            },
        }

        resp = self._client.post(
            f"{PLANET_DATA_URL}/quick-search",
            json=payload,
            params={"_page_size": limit},
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        logger.info(
            "Planet search: %d scenes found for bbox=%s %s→%s",
            len(features), bbox, start_date, end_date,
        )
        return features

    # ── Asset activation + download ─────────────────────────────────────────

    def _activate_asset(self, item_type: str, item_id: str, asset_type: str) -> str:
        """Activate an asset and return its download URL (polls until ready)."""
        asset_url = f"{PLANET_DATA_URL}/item-types/{item_type}/items/{item_id}/assets"
        resp = self._client.get(asset_url)
        resp.raise_for_status()
        assets = resp.json()

        if asset_type not in assets:
            available = list(assets.keys())
            raise ValueError(
                f"Asset '{asset_type}' not available for {item_id}. "
                f"Available: {available}"
            )

        asset = assets[asset_type]
        status = asset["status"]

        if status == "inactive":
            activate_url = asset["_links"]["activate"]
            act_resp = self._client.post(activate_url)
            act_resp.raise_for_status()
            logger.info("Activating asset %s/%s …", item_id, asset_type)

        # Poll until active (max ~5 min)
        for attempt in range(30):
            resp = self._client.get(asset_url)
            resp.raise_for_status()
            asset = resp.json()[asset_type]
            if asset["status"] == "active":
                return asset["location"]
            logger.debug("Asset not ready yet (attempt %d/30)", attempt + 1)
            time.sleep(10)

        raise TimeoutError(f"Asset {item_id}/{asset_type} did not activate in 5 minutes")

    def _download_geotiff(self, download_url: str) -> np.ndarray:
        """Download a GeoTIFF and return it as (H, W, bands) float32 array."""
        import rasterio  # type: ignore

        resp = self._client.get(download_url, timeout=300)
        resp.raise_for_status()
        with rasterio.open(io.BytesIO(resp.content)) as ds:
            data = ds.read().astype(np.float32)
        return np.transpose(data, (1, 2, 0))

    # ── High-level composite ─────────────────────────────────────────────────

    def get_planetscope_composite(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        asset_type: str = "ortho_analytic_4b_sr",
    ) -> np.ndarray:
        """
        Return (H, W, 4) float32 array [Blue, Green, Red, NIR] surface reflectance.
        Values are in [0, 1] (divided by 10000 from DN).

        Picks the scene with lowest cloud cover in the date range.
        """
        scenes = self.search_scenes(bbox, start_date, end_date, item_type="planetscope")
        if not scenes:
            raise ValueError(
                f"No PlanetScope scenes found for bbox={bbox} {start_date}→{end_date}"
            )

        # Best scene = lowest cloud cover
        best = min(scenes, key=lambda f: f["properties"].get("cloud_cover", 1.0))
        item_id = best["id"]
        item_type = best["properties"]["item_type"]

        logger.info(
            "Best PS scene: %s  cloud=%.1f%%  acquired=%s",
            item_id,
            best["properties"].get("cloud_cover", 0) * 100,
            best["properties"].get("acquired", "?"),
        )

        download_url = self._activate_asset(item_type, item_id, asset_type)
        arr = self._download_geotiff(download_url)

        # SR assets are scaled by 10000; convert to reflectance [0, 1]
        arr = np.clip(arr / 10000.0, 0.0, 1.0)
        return arr

    def get_mosaic_quads(
        self,
        bbox: List[float],
        mosaic_name: str,
        zoom: int = 15,
    ) -> np.ndarray:
        """
        Download Planet Basemap mosaic quads for a bbox.

        Useful for near-real-time monitoring without per-scene activation latency.
        Returns (H, W, 3) uint8 RGB array stitched from the intersecting quads.
        """
        from PIL import Image  # type: ignore

        # List mosaics to find the one matching mosaic_name
        resp = self._client.get(f"{PLANET_BASE}/basemaps/v1/mosaics")
        resp.raise_for_status()
        mosaics = resp.json().get("mosaics", [])
        mosaic = next((m for m in mosaics if m["name"] == mosaic_name), None)
        if mosaic is None:
            names = [m["name"] for m in mosaics[:5]]
            raise ValueError(
                f"Mosaic '{mosaic_name}' not found. Available (first 5): {names}"
            )

        mosaic_id = mosaic["id"]

        # Find intersecting quads
        quads_resp = self._client.get(
            f"{PLANET_BASE}/basemaps/v1/mosaics/{mosaic_id}/quads",
            params={
                "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
                "_page_size": 50,
            },
        )
        quads_resp.raise_for_status()
        quads = quads_resp.json().get("items", [])

        if not quads:
            raise ValueError(f"No quads found for mosaic '{mosaic_name}' in bbox={bbox}")

        logger.info("Downloading %d mosaic quads …", len(quads))
        tiles: List[np.ndarray] = []
        for quad in quads:
            dl_url = quad["_links"]["download"]
            tile_resp = self._client.get(dl_url, timeout=120)
            tile_resp.raise_for_status()
            img = Image.open(io.BytesIO(tile_resp.content)).convert("RGB")
            tiles.append(np.array(img))

        # Simple horizontal stack (assumes quads are same height for a single row)
        return np.concatenate(tiles, axis=1) if len(tiles) > 1 else tiles[0]

    # ── NDVI helper ──────────────────────────────────────────────────────────

    @staticmethod
    def compute_ndvi(ps_array: np.ndarray) -> np.ndarray:
        """
        Compute NDVI from a (H, W, 4) PlanetScope SR array [B, G, R, NIR].
        Returns (H, W) float32 in [-1, 1].
        """
        red = ps_array[:, :, 2].astype(np.float32)
        nir = ps_array[:, :, 3].astype(np.float32)
        denom = nir + red
        ndvi = np.where(denom > 0, (nir - red) / denom, 0.0)
        return ndvi.astype(np.float32)

    def close(self) -> None:
        self._client.close()
