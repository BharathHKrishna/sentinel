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
from scipy.ndimage import uniform_filter

from apps.api.services.change.generic import compute_ndbi


def _glcm_contrast_map(
    band: np.ndarray,
    patch_size: int = 15,
) -> np.ndarray:
    """
    Approximate per-pixel GLCM contrast (distance=1, angle=0, symmetric) using
    a vectorised local mean instead of a per-pixel skimage.graycomatrix call.

    For that offset, GLCM "contrast" = sum_i,j (i-j)^2 * P(i,j) reduces exactly
    to the local mean of squared differences between horizontally-adjacent
    quantised pixel pairs — a per-pixel Python loop over graycomatrix was
    ~13k calls per 128x128 image and dominated scan latency.

    Parameters
    ----------
    band       : 2-D float32 array in [0, 1]
    patch_size : half-window size (final window = 2*patch_size + 1)

    Returns
    -------
    contrast : 2-D float32 array, same spatial dims as `band`
    """
    h, w = band.shape
    # Quantise to 64 grey levels (truncating, matching the old uint8 cast)
    grey = np.clip((band * 63).astype(np.uint8), 0, 63).astype(np.float32)
    half = patch_size

    # diff_sq[:, c] is the squared diff of the pixel pair (c, c+1); a patch
    # centred on column x spans diff columns [x-half, x+half-1] (2*half of
    # them), while rows stay centred at y over [y-half, y+half] (2*half+1).
    diff_sq = (grey[:, 1:] - grey[:, :-1]) ** 2  # (h, w-1) horizontal pair diffs
    local_mean = uniform_filter(diff_sq, size=(2 * half + 1, 2 * half), mode="nearest")

    contrast = np.zeros((h, w), dtype=np.float32)
    contrast[:, : w - 1] = local_mean

    # Original loop only ever filled y/x in [half, h-half)/[half, w-half);
    # keep boundary pixels at 0 to match that behaviour.
    contrast[:half, :] = 0.0
    contrast[h - half:, :] = 0.0
    contrast[:, :half] = 0.0
    contrast[:, w - half:] = 0.0

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
