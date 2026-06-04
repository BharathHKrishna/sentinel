"""
Generic change detector.

Computes spectral indices (NDVI, NDBI, NDWI) from before/after S2 bands,
returns a binary change mask and a float magnitude array.

Band order (index → band):
  0: B01  1: B02 (Blue)   2: B03 (Green)  3: B04 (Red)
  4: B05  5: B06           6: B07           7: B08 (NIR)
  8: B8A  9: B09          10: B11 (SWIR1)  11: B12 (SWIR2)
"""
from typing import Tuple

import numpy as np


def _safe_norm(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b), with division-by-zero protected."""
    denom = a + b
    return np.where(denom != 0, (a - b) / denom, 0.0).astype(np.float32)


def compute_ndvi(s2: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - Red) / (NIR + Red).  Band 7 = B08, Band 3 = B04."""
    nir = s2[:, :, 7]
    red = s2[:, :, 3]
    return _safe_norm(nir, red)


def compute_ndbi(s2: np.ndarray) -> np.ndarray:
    """NDBI = (SWIR1 - NIR) / (SWIR1 + NIR).  Band 10 = B11, Band 7 = B08."""
    swir1 = s2[:, :, 10]
    nir = s2[:, :, 7]
    return _safe_norm(swir1, nir)


def compute_ndwi(s2: np.ndarray) -> np.ndarray:
    """NDWI = (Green - NIR) / (Green + NIR).  Band 2 = B03, Band 7 = B08."""
    green = s2[:, :, 2]
    nir = s2[:, :, 7]
    return _safe_norm(green, nir)


class GenericChangeDetector:
    """
    Detects generic spectral change between two S2 composites.

    Parameters
    ----------
    threshold : float
        Minimum magnitude of combined index change to flag a pixel (0–1).
    """

    def __init__(self, threshold: float = 0.15) -> None:
        self.threshold = threshold

    def detect(
        self,
        before: np.ndarray,
        after: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Parameters
        ----------
        before, after : np.ndarray of shape (H, W, 12), float32, [0, 1]

        Returns
        -------
        mask      : bool array (H, W) — True where significant change occurred
        magnitude : float32 array (H, W) — combined spectral change [0, 1]
        """
        ndvi_before = compute_ndvi(before)
        ndvi_after = compute_ndvi(after)
        ndvi_delta = ndvi_after - ndvi_before  # negative = vegetation loss

        ndbi_before = compute_ndbi(before)
        ndbi_after = compute_ndbi(after)
        ndbi_delta = ndbi_after - ndbi_before  # positive = built-up increase

        ndwi_before = compute_ndwi(before)
        ndwi_after = compute_ndwi(after)
        ndwi_delta = ndwi_after - ndwi_before

        # Combined magnitude: max absolute change across all indices
        magnitude = np.maximum(
            np.abs(ndvi_delta),
            np.maximum(np.abs(ndbi_delta), np.abs(ndwi_delta)),
        ).astype(np.float32)

        mask = magnitude >= self.threshold
        return mask, magnitude
