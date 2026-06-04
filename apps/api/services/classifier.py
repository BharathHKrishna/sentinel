"""
EventClassifier

Orchestrates all change detectors for a given before/after imagery pair
and returns the best-match event type and confidence score.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from apps.api.services.change.generic import GenericChangeDetector
from apps.api.services.change.construction import ConstructionDetector
from apps.api.services.change.deforestation import DeforestationDetector
from apps.api.services.change.fire import FireDetector
from apps.api.services.change.flood import FloodDetector
from apps.api.services.change.solar import SolarDetector

logger = logging.getLogger(__name__)

KNOWN_TYPES = ["construction", "deforestation", "fire", "flood", "solar"]


@dataclass
class ClassificationResult:
    detected_type: str
    confidence: float
    mask: np.ndarray
    lat: Optional[float]
    lon: Optional[float]
    all_scores: Dict[str, float]


class EventClassifier:
    """
    Runs a configurable set of change detectors and picks the one with the
    highest confidence above a minimum threshold.

    Parameters
    ----------
    detection_types : list of str
        Which detectors to run (subset of KNOWN_TYPES).  If empty, all run.
    min_confidence  : float
        Detections below this threshold are discarded.
    bbox            : [min_lon, min_lat, max_lon, max_lat]
        Used to compute lat/lon centroid of the detection and for VIIRS check.
    """

    def __init__(
        self,
        detection_types: List[str] | None = None,
        min_confidence: float = 0.25,
        bbox: List[float] | None = None,
    ) -> None:
        self.detection_types = detection_types or KNOWN_TYPES
        self.min_confidence = min_confidence
        self.bbox = bbox

        self._generic = GenericChangeDetector()
        self._detectors: Dict[str, object] = {
            "construction": ConstructionDetector(),
            "deforestation": DeforestationDetector(),
            "fire": FireDetector(bbox=bbox),
            "solar": SolarDetector(),
        }
        self._flood_detector = FloodDetector()

    def classify(
        self,
        before_s2: np.ndarray,
        after_s2: np.ndarray,
        before_sar: Optional[np.ndarray] = None,
        after_sar: Optional[np.ndarray] = None,
    ) -> Optional[ClassificationResult]:
        """
        Run all requested detectors and return the highest-confidence result,
        or None if no detector exceeds `min_confidence`.

        Parameters
        ----------
        before_s2, after_s2 : (H, W, 12) float32
        before_sar, after_sar : (H, W, 2) float32 — optional SAR arrays
        """
        # Quick pre-filter: if generic detector finds no significant change at all,
        # skip expensive per-type detectors.
        generic_mask, generic_mag = self._generic.detect(before_s2, after_s2)
        if generic_mask.sum() == 0:
            logger.debug("No significant spectral change detected — skipping typed detectors")
            return None

        scores: Dict[str, Tuple[np.ndarray, float]] = {}

        for det_type in self.detection_types:
            if det_type == "flood":
                if before_sar is not None and after_sar is not None:
                    mask, conf = self._flood_detector.detect(before_sar, after_sar, after_s2)
                    scores["flood"] = (mask, conf)
                else:
                    logger.debug("SAR data not available — skipping flood detection")
                continue

            detector = self._detectors.get(det_type)
            if detector is None:
                continue

            try:
                mask, conf = detector.detect(before_s2, after_s2)  # type: ignore[call-arg]
                scores[det_type] = (mask, conf)
                logger.debug("Detector %s: confidence=%.3f, pixels=%d", det_type, conf, mask.sum())
            except Exception as exc:
                logger.warning("Detector %s failed: %s", det_type, exc)

        if not scores:
            return None

        # Pick the highest confidence detection
        best_type, (best_mask, best_conf) = max(
            scores.items(), key=lambda kv: kv[1][1]
        )

        if best_conf < self.min_confidence:
            logger.debug(
                "Best confidence %.3f below threshold %.3f", best_conf, self.min_confidence
            )
            return None

        # Compute centroid lat/lon from the mask if bbox is known
        lat, lon = self._mask_centroid(best_mask)

        return ClassificationResult(
            detected_type=best_type,
            confidence=best_conf,
            mask=best_mask,
            lat=lat,
            lon=lon,
            all_scores={k: v[1] for k, v in scores.items()},
        )

    def _mask_centroid(self, mask: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
        """Return geographic centroid of the True pixels, or (None, None)."""
        if self.bbox is None or mask.sum() == 0:
            return None, None

        ys, xs = np.where(mask)
        h, w = mask.shape
        cy = float(ys.mean()) / h  # normalised [0, 1]
        cx = float(xs.mean()) / w

        min_lon, min_lat, max_lon, max_lat = self.bbox
        lon = min_lon + cx * (max_lon - min_lon)
        lat = max_lat - cy * (max_lat - min_lat)  # y=0 → north
        return round(lat, 6), round(lon, 6)
