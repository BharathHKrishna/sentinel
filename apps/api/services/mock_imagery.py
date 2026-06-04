"""
Mock imagery provider for local development and CI.

Generates synthetic Sentinel-2 and SAR numpy arrays that mimic real
satellite composites well enough to exercise the full change detection
pipeline without actual satellite API credentials.

Each provider generates a spatially coherent "before" scene and an "after"
scene where a configurable change has been injected, so the detectors will
fire at realistic confidence levels.
"""
import random
from typing import Optional

import numpy as np


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_s2(h: int = 128, w: int = 128, seed: int = 0) -> np.ndarray:
    """
    Generate a realistic-looking S2 scene with vegetation, bare soil, and
    water patches — no strong signal for any anomaly type.

    Band layout (12 bands):
      0=B01  1=B02(Blue)  2=B03(Green)  3=B04(Red)
      4=B05  5=B06        6=B07         7=B08(NIR)
      8=B8A  9=B09       10=B11(SWIR1) 11=B12(SWIR2)
    """
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 12), dtype=np.float32)

    # Vegetation patches (~60% of area): high NIR, moderate Green, low Red
    veg_mask = rng.random((h, w)) > 0.4
    arr[:, :, 7][veg_mask] = rng.uniform(0.5, 0.75, veg_mask.sum())   # NIR
    arr[:, :, 3][veg_mask] = rng.uniform(0.05, 0.12, veg_mask.sum())  # Red
    arr[:, :, 2][veg_mask] = rng.uniform(0.10, 0.20, veg_mask.sum())  # Green
    arr[:, :, 1][veg_mask] = rng.uniform(0.05, 0.15, veg_mask.sum())  # Blue

    # Bare soil patches (~30%): moderate SWIR, moderate Red
    soil_mask = (~veg_mask) & (rng.random((h, w)) > 0.33)
    arr[:, :, 7][soil_mask] = rng.uniform(0.2, 0.35, soil_mask.sum())
    arr[:, :, 3][soil_mask] = rng.uniform(0.15, 0.25, soil_mask.sum())
    arr[:, :, 10][soil_mask] = rng.uniform(0.2, 0.35, soil_mask.sum())

    # Water patches (~10%): low everything, slight Blue/Green
    water_mask = ~veg_mask & ~soil_mask
    arr[:, :, 1][water_mask] = rng.uniform(0.03, 0.08, water_mask.sum())
    arr[:, :, 2][water_mask] = rng.uniform(0.03, 0.07, water_mask.sum())
    arr[:, :, 7][water_mask] = rng.uniform(0.01, 0.04, water_mask.sum())

    # Fill remaining bands with low noise
    for b in [0, 4, 5, 6, 8, 9, 11]:
        arr[:, :, b] = rng.uniform(0.02, 0.12, (h, w)).astype(np.float32)

    return np.clip(arr, 0.0, 1.0)


def _inject_construction(base: np.ndarray, fraction: float = 0.25) -> np.ndarray:
    """Inject a construction zone: raise SWIR1, lower NIR in a rectangular patch."""
    arr = base.copy()
    h, w = arr.shape[:2]
    ph, pw = int(h * fraction), int(w * fraction)
    r0, c0 = h // 4, w // 4
    arr[r0:r0+ph, c0:c0+pw, 10] = 0.55   # SWIR1 high (built-up)
    arr[r0:r0+ph, c0:c0+pw, 7]  = 0.18   # NIR low
    arr[r0:r0+ph, c0:c0+pw, 3]  = 0.22   # Red moderate (bare earth)
    return np.clip(arr, 0.0, 1.0)


def _inject_deforestation(base: np.ndarray, fraction: float = 0.3) -> np.ndarray:
    """Inject a cleared forest patch: drop NIR sharply in a patch."""
    arr = base.copy()
    h, w = arr.shape[:2]
    ph, pw = int(h * fraction), int(w * fraction)
    r0, c0 = h // 3, w // 3
    arr[r0:r0+ph, c0:c0+pw, 7] = 0.12    # NIR drops
    arr[r0:r0+ph, c0:c0+pw, 3] = 0.20    # Red increases (bare)
    return np.clip(arr, 0.0, 1.0)


def _inject_fire(base: np.ndarray, fraction: float = 0.25) -> np.ndarray:
    """Inject a burn scar: low NIR, high SWIR2 (NBR drops)."""
    arr = base.copy()
    h, w = arr.shape[:2]
    ph, pw = int(h * fraction), int(w * fraction)
    r0, c0 = h // 4, w // 2
    arr[r0:r0+ph, c0:c0+pw, 7]  = 0.08   # NIR very low
    arr[r0:r0+ph, c0:c0+pw, 11] = 0.55   # SWIR2 high
    return np.clip(arr, 0.0, 1.0)


def _inject_solar(base: np.ndarray, fraction: float = 0.20) -> np.ndarray:
    """Inject solar panels: high SWIR1, very low NDVI."""
    arr = base.copy()
    h, w = arr.shape[:2]
    ph, pw = int(h * fraction), int(w * fraction)
    r0, c0 = h // 2, w // 4
    arr[r0:r0+ph, c0:c0+pw, 10] = 0.55   # SWIR1 high
    arr[r0:r0+ph, c0:c0+pw, 7]  = 0.12   # NIR low
    arr[r0:r0+ph, c0:c0+pw, 3]  = 0.08   # Red very low (dark panels)
    return np.clip(arr, 0.0, 1.0)


def _base_sar(h: int = 128, w: int = 128, seed: int = 0) -> np.ndarray:
    """Synthetic SAR scene (H, W, 2) [VV, VH] in dB. Land ~ -8 to -4 dB."""
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 2), dtype=np.float32)
    arr[:, :, 0] = rng.uniform(-10.0, -4.0, (h, w)).astype(np.float32)   # VV
    arr[:, :, 1] = rng.uniform(-16.0, -10.0, (h, w)).astype(np.float32)  # VH
    return arr


def _inject_flood_sar(sar: np.ndarray, fraction: float = 0.30) -> np.ndarray:
    """Inject flooding: drop VV backscatter (open water → very low VV)."""
    arr = sar.copy()
    h, w = arr.shape[:2]
    ph, pw = int(h * fraction), int(w * fraction)
    r0, c0 = h // 3, w // 3
    arr[r0:r0+ph, c0:c0+pw, 0] = -22.0   # VV very low (open water)
    return arr


# ── Public API ────────────────────────────────────────────────────────────────

class MockImageryProvider:
    """
    Generates synthetic before/after S2 and SAR arrays for a given change type.

    Usage:
        provider = MockImageryProvider(change_type="construction")
        before_s2 = provider.before_s2()
        after_s2  = provider.after_s2()
        # Run through change detectors — will produce realistic detections.
    """

    CHANGE_TYPES = ["construction", "deforestation", "fire", "flood", "solar"]

    def __init__(
        self,
        change_type: Optional[str] = None,
        h: int = 128,
        w: int = 128,
        seed: int = 42,
    ) -> None:
        if change_type is None:
            change_type = random.choice(self.CHANGE_TYPES)
        self.change_type = change_type
        self._h = h
        self._w = w
        self._seed = seed
        self._base = _base_s2(h, w, seed)
        self._base_sar = _base_sar(h, w, seed)

    def before_s2(self) -> np.ndarray:
        return self._base.copy()

    def after_s2(self) -> np.ndarray:
        injectors = {
            "construction": _inject_construction,
            "deforestation": _inject_deforestation,
            "fire": _inject_fire,
            "solar": _inject_solar,
            "flood": lambda x: x,   # flood is SAR-based
        }
        fn = injectors.get(self.change_type, lambda x: x)
        return fn(self._base)

    def before_sar(self) -> np.ndarray:
        return self._base_sar.copy()

    def after_sar(self) -> np.ndarray:
        if self.change_type == "flood":
            return _inject_flood_sar(self._base_sar)
        return self._base_sar.copy()

    @classmethod
    def for_region(cls, detection_types: list, seed: int = 42) -> "MockImageryProvider":
        """Pick the most likely change type for a region's detection config."""
        if detection_types:
            valid = [t for t in detection_types if t in cls.CHANGE_TYPES]
            change_type = valid[0] if valid else detection_types[0]
        else:
            change_type = "construction"
        return cls(change_type=change_type, seed=seed)
