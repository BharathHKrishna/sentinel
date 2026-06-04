"""
Deforestation change detector.

Strategy:
  - Compute NDVI for before and after S2 composites.
  - Establish a "forest baseline": pixels with NDVI > forest_baseline_ndvi.
  - Flag pixels where NDVI drops by more than ndvi_decline_threshold AND the
    before-NDVI indicated forest cover.
  - Confidence is proportional to the mean NDVI decline in flagged pixels.
"""
from typing import Tuple

import numpy as np

from apps.api.services.change.generic import compute_ndvi


class DeforestationDetector:
    """
    Detects forest clearing by monitoring significant NDVI decline in areas
    that previously had high vegetation cover.
    """

    def __init__(
        self,
        forest_baseline_ndvi: float = 0.5,
        ndvi_decline_threshold: float = 0.2,
    ) -> None:
        self.forest_baseline_ndvi = forest_baseline_ndvi
        self.ndvi_decline_threshold = ndvi_decline_threshold

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
        mask       : bool (H, W) — True where deforestation likely occurred
        confidence : float [0, 1]
        """
        ndvi_before = compute_ndvi(before)
        ndvi_after = compute_ndvi(after)

        # Only consider pixels that were previously forested
        was_forest = ndvi_before >= self.forest_baseline_ndvi
        ndvi_decline = ndvi_before - ndvi_after  # positive = vegetation loss

        mask = was_forest & (ndvi_decline >= self.ndvi_decline_threshold)

        if mask.sum() == 0:
            return mask, 0.0

        mean_decline = float(ndvi_decline[mask].mean())
        # Normalise: 0.2 decline → 0.4 confidence, 0.5 decline → 1.0
        confidence = float(np.clip(mean_decline / 0.5, 0.0, 1.0))
        return mask, confidence
