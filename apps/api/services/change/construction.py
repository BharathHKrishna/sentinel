"""
Construction change detector.

Strategy:
  1. Compute NDBI delta (built-up increase) between before/after S2 composites.
  2. Compute GLCM contrast texture on the before NIR band (smooth = bare soil/
     construction, high texture = existing urban).
  3. Flag pixels where NDBI increases by > ndbi_threshold AND texture contrast
     stays below contrast_threshold (new, uniform surfaces).
"""
from typing import Tuple

import numpy as np
from skimage.feature import graycomatrix, graycoprops  # type: ignore
from skimage.util import img_as_ubyte  # type: ignore

from apps.api.services.change.generic import compute_ndbi


def _glcm_contrast_map(
    band: np.ndarray,
    patch_size: int = 15,
) -> np.ndarray:
    """
    Compute per-pixel GLCM contrast using a sliding window.

    Parameters
    ----------
    band       : 2-D float32 array in [0, 1]
    patch_size : half-window size (final window = 2*patch_size + 1)

    Returns
    -------
    contrast : 2-D float32 array, same spatial dims as `band`
    """
    h, w = band.shape
    # Quantise to 64 grey levels for speed
    grey = np.clip((band * 63).astype(np.uint8), 0, 63)
    contrast = np.zeros((h, w), dtype=np.float32)
    half = patch_size

    for y in range(half, h - half):
        for x in range(half, w - half):
            patch = grey[y - half : y + half + 1, x - half : x + half + 1]
            glcm = graycomatrix(
                patch,
                distances=[1],
                angles=[0],
                levels=64,
                symmetric=True,
                normed=True,
            )
            contrast[y, x] = graycoprops(glcm, "contrast")[0, 0]

    return contrast


class ConstructionDetector:
    """
    Detects new construction by combining NDBI increase and low texture
    contrast (smooth bare earth / freshly built surfaces).
    """

    def __init__(
        self,
        ndbi_threshold: float = 0.12,
        contrast_threshold: float = 1.5,
        patch_size: int = 7,
    ) -> None:
        self.ndbi_threshold = ndbi_threshold
        self.contrast_threshold = contrast_threshold
        self.patch_size = patch_size

    def detect(
        self,
        before: np.ndarray,
        after: np.ndarray,
    ) -> Tuple[np.ndarray, float]:
        """
        Parameters
        ----------
        before, after : (H, W, 12) float32 S2 arrays

        Returns
        -------
        mask       : bool (H, W) — True where construction likely occurred
        confidence : float [0, 1] — fraction of changed pixels * signal strength
        """
        ndbi_before = compute_ndbi(before)
        ndbi_after = compute_ndbi(after)
        ndbi_delta = ndbi_after - ndbi_before  # positive = new built-up

        nir_after = after[:, :, 7]  # B08
        contrast = _glcm_contrast_map(nir_after, patch_size=self.patch_size)

        # Construction: built-up increases AND surface is relatively smooth
        mask = (ndbi_delta >= self.ndbi_threshold) & (contrast <= self.contrast_threshold)

        if mask.sum() == 0:
            return mask, 0.0

        # Confidence: mean NDBI delta in changed pixels, normalised to [0, 1]
        mean_delta = float(ndbi_delta[mask].mean())
        # NDBI delta range is roughly [-2, 2], normalise to [0, 1]
        confidence = float(np.clip(mean_delta / 0.5, 0.0, 1.0))
        return mask, confidence
