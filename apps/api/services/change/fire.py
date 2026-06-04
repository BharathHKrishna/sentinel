"""
Fire / burn scar change detector.

Strategy:
  1. Compute NBR (Normalized Burn Ratio) = (NIR - SWIR2) / (NIR + SWIR2)
     for before and after S2 composites.
  2. dNBR = NBR_before - NBR_after  (positive = burn severity)
  3. Cross-check with VIIRS active fire / FIRMS API for the same bbox/date.
  4. Confidence is derived from mean dNBR in flagged pixels + VIIRS confirmation.

VIIRS active fire endpoint (NASA FIRMS):
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/VIIRS_SNPP_NRT/<bbox>/<days>
"""
import os
import logging
from typing import List, Tuple

import httpx
import numpy as np

logger = logging.getLogger(__name__)

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def compute_nbr(s2: np.ndarray) -> np.ndarray:
    """NBR = (NIR - SWIR2) / (NIR + SWIR2).  Band 7 = B08, Band 11 = B12."""
    nir = s2[:, :, 7]
    swir2 = s2[:, :, 11]
    denom = nir + swir2
    return np.where(denom != 0, (nir - swir2) / denom, 0.0).astype(np.float32)


def query_viirs_active_fires(
    bbox: List[float],
    days: int = 7,
) -> int:
    """
    Query NASA FIRMS VIIRS NRT endpoint for active fire detections.

    Returns the number of fire detections in the bbox over the last `days`.
    Returns 0 on any error (graceful degradation).
    """
    map_key = os.environ.get("NASA_FIRMS_MAP_KEY", "")
    if not map_key:
        logger.debug("NASA_FIRMS_MAP_KEY not set — skipping VIIRS check")
        return 0

    # FIRMS API: /csv/<key>/VIIRS_SNPP_NRT/<W,S,E,N>/<days>
    w, s, e, n = bbox[0], bbox[1], bbox[2], bbox[3]
    url = f"{FIRMS_BASE}/{map_key}/VIIRS_SNPP_NRT/{w},{s},{e},{n}/{days}"

    try:
        resp = httpx.get(url, timeout=20)
        resp.raise_for_status()
        # CSV: first line is header
        lines = [l for l in resp.text.strip().splitlines() if l]
        return max(0, len(lines) - 1)  # subtract header row
    except Exception as exc:
        logger.warning("VIIRS query failed: %s", exc)
        return 0


class FireDetector:
    """
    Detects fire burn scars using dNBR and optional VIIRS active fire
    cross-checking.
    """

    def __init__(
        self,
        dnbr_threshold: float = 0.1,
        high_severity_dnbr: float = 0.44,
        bbox: List[float] | None = None,
    ) -> None:
        self.dnbr_threshold = dnbr_threshold
        self.high_severity_dnbr = high_severity_dnbr
        self.bbox = bbox  # optional; used for VIIRS cross-check

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
        mask       : bool (H, W)
        confidence : float [0, 1]
        """
        nbr_before = compute_nbr(before)
        nbr_after = compute_nbr(after)
        dnbr = nbr_before - nbr_after  # positive = burn severity

        mask = dnbr >= self.dnbr_threshold

        if mask.sum() == 0:
            return mask, 0.0

        mean_dnbr = float(dnbr[mask].mean())
        # Normalise: 0.1 → low, 0.44+ → high severity
        spectral_confidence = float(np.clip(mean_dnbr / self.high_severity_dnbr, 0.0, 1.0))

        # VIIRS cross-check: add 0.15 bonus if fires confirmed
        viirs_bonus = 0.0
        if self.bbox:
            fire_count = query_viirs_active_fires(self.bbox)
            if fire_count > 0:
                logger.info("VIIRS confirmed %d active fire pixels", fire_count)
                viirs_bonus = 0.15

        confidence = float(np.clip(spectral_confidence + viirs_bonus, 0.0, 1.0))
        return mask, confidence
