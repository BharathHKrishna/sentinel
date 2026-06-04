"""
Flood change detector using Sentinel-1 SAR.

Strategy:
  - Compare VV-polarisation backscatter (dB) between before/after S1 composites.
  - Open water reflects SAR away from the sensor → very low VV backscatter.
  - A significant decrease in VV backscatter in non-urban areas indicates
    surface inundation.
  - Urban areas are excluded using a NDBI mask from the S2 composite.
"""
from typing import Tuple

import numpy as np

from apps.api.services.change.generic import compute_ndbi


class FloodDetector:
    """
    Detects flood inundation via Sentinel-1 VV backscatter decrease.

    Parameters
    ----------
    vv_decrease_threshold : float
        Minimum VV backscatter decrease (dB) to flag a pixel as flooded.
        Typical values: 3–5 dB.
    urban_ndbi_threshold : float
        NDBI above this value is treated as urban and excluded.
    """

    def __init__(
        self,
        vv_decrease_threshold: float = 4.0,
        urban_ndbi_threshold: float = 0.1,
    ) -> None:
        self.vv_decrease_threshold = vv_decrease_threshold
        self.urban_ndbi_threshold = urban_ndbi_threshold

    def detect(
        self,
        before_sar: np.ndarray,
        after_sar: np.ndarray,
        after_s2: np.ndarray | None = None,
    ) -> Tuple[np.ndarray, float]:
        """
        Parameters
        ----------
        before_sar : (H, W, 2) float32 — [VV, VH] in dB
        after_sar  : (H, W, 2) float32 — [VV, VH] in dB
        after_s2   : (H, W, 12) float32 — optional S2 for urban mask

        Returns
        -------
        mask       : bool (H, W)
        confidence : float [0, 1]
        """
        vv_before = before_sar[:, :, 0]  # VV channel
        vv_after = after_sar[:, :, 0]
        vv_delta = vv_before - vv_after  # positive = backscatter decreased

        flood_candidate = vv_delta >= self.vv_decrease_threshold

        # Exclude urban / built-up pixels if S2 data is available
        if after_s2 is not None:
            ndbi = compute_ndbi(after_s2)
            # Resize NDBI to match SAR dimensions if needed
            if ndbi.shape != vv_delta.shape:
                from skimage.transform import resize  # type: ignore
                ndbi = resize(ndbi, vv_delta.shape, preserve_range=True).astype(np.float32)
            urban_mask = ndbi >= self.urban_ndbi_threshold
            flood_candidate = flood_candidate & ~urban_mask

        mask = flood_candidate

        if mask.sum() == 0:
            return mask, 0.0

        mean_decrease = float(vv_delta[mask].mean())
        # Normalise: 4 dB decrease → ~0.5 confidence; 10 dB → ~1.0
        confidence = float(np.clip((mean_decrease - self.vv_decrease_threshold) / 6.0, 0.0, 1.0))
        # Ensure minimum confidence if mask is non-empty
        confidence = max(confidence, 0.3)
        return mask, confidence
