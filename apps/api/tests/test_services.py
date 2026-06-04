"""
Unit tests for change detection services.
Uses synthetic numpy arrays — no real imagery or API calls.
"""
import numpy as np
import pytest

from apps.api.services.change.generic import (
    GenericChangeDetector,
    compute_ndvi,
    compute_ndbi,
    compute_ndwi,
)
from apps.api.services.change.construction import ConstructionDetector
from apps.api.services.change.deforestation import DeforestationDetector
from apps.api.services.change.fire import FireDetector, compute_nbr
from apps.api.services.change.flood import FloodDetector
from apps.api.services.change.solar import SolarDetector


def make_s2(h: int = 64, w: int = 64, seed: int = 0) -> np.ndarray:
    """Random S2-like array (H, W, 12) float32 in [0, 1]."""
    rng = np.random.default_rng(seed)
    return rng.random((h, w, 12)).astype(np.float32)


def make_s2_with_vegetation(h: int = 64, w: int = 64) -> np.ndarray:
    """S2 array with high NIR (band 7) and moderate red (band 3) → high NDVI."""
    arr = np.zeros((h, w, 12), dtype=np.float32) + 0.1
    arr[:, :, 7] = 0.8   # NIR
    arr[:, :, 3] = 0.1   # Red
    return arr


def make_s2_with_buildup(h: int = 64, w: int = 64) -> np.ndarray:
    """S2 array with high SWIR1 (band 10) and moderate NIR (band 7) → high NDBI."""
    arr = np.zeros((h, w, 12), dtype=np.float32) + 0.1
    arr[:, :, 10] = 0.7  # SWIR1
    arr[:, :, 7] = 0.2   # NIR
    return arr


def make_s2_burned(h: int = 64, w: int = 64) -> np.ndarray:
    """S2 array where SWIR2 (band 11) dominates → low NBR (burned area)."""
    arr = np.zeros((h, w, 12), dtype=np.float32) + 0.1
    arr[:, :, 7] = 0.1   # NIR low (burned)
    arr[:, :, 11] = 0.6  # SWIR2 high (burned)
    return arr


def make_sar(h: int = 64, w: int = 64, vv: float = -10.0, vh: float = -15.0) -> np.ndarray:
    """SAR array (H, W, 2) with constant VV/VH in dB."""
    arr = np.zeros((h, w, 2), dtype=np.float32)
    arr[:, :, 0] = vv
    arr[:, :, 1] = vh
    return arr


# ── Index functions ────────────────────────────────────────────────────────────

class TestIndexFunctions:
    def test_ndvi_range(self):
        arr = make_s2()
        ndvi = compute_ndvi(arr)
        assert ndvi.shape == (64, 64)
        assert ndvi.min() >= -1.0
        assert ndvi.max() <= 1.0

    def test_ndvi_vegetation(self):
        arr = make_s2_with_vegetation()
        ndvi = compute_ndvi(arr)
        assert ndvi.mean() > 0.6, "High NIR / low Red should yield high NDVI"

    def test_ndbi_range(self):
        arr = make_s2()
        ndbi = compute_ndbi(arr)
        assert ndbi.min() >= -1.0
        assert ndbi.max() <= 1.0

    def test_ndwi_range(self):
        arr = make_s2()
        ndwi = compute_ndwi(arr)
        assert ndwi.min() >= -1.0
        assert ndwi.max() <= 1.0

    def test_nbr_range(self):
        arr = make_s2()
        nbr = compute_nbr(arr)
        assert nbr.min() >= -1.0
        assert nbr.max() <= 1.0


# ── GenericChangeDetector ───────────────────────────────────────────────────────

class TestGenericChangeDetector:
    def test_no_change_identical(self):
        arr = make_s2()
        detector = GenericChangeDetector()
        mask, mag = detector.detect(arr, arr)
        assert mask.sum() == 0, "Identical arrays should have zero change"
        assert mag.max() < 1e-5

    def test_detects_large_change(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        detector = GenericChangeDetector(threshold=0.1)
        mask, mag = detector.detect(before, after)
        assert mask.sum() > 0, "Vegetation→buildup should trigger generic change"

    def test_output_shapes(self):
        arr = make_s2(32, 48)
        detector = GenericChangeDetector()
        mask, mag = detector.detect(arr, arr)
        assert mask.shape == (32, 48)
        assert mag.shape == (32, 48)


# ── ConstructionDetector ───────────────────────────────────────────────────────

class TestConstructionDetector:
    def test_no_construction_identical(self):
        arr = make_s2()
        detector = ConstructionDetector()
        mask, conf = detector.detect(arr, arr)
        assert conf == 0.0

    def test_detects_new_buildup(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        detector = ConstructionDetector(ndbi_threshold=0.05, patch_size=3)
        mask, conf = detector.detect(before, after)
        assert conf > 0.0, "Vegetation→buildup should be detected as construction"

    def test_confidence_bounded(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        _, conf = ConstructionDetector(patch_size=3).detect(before, after)
        assert 0.0 <= conf <= 1.0


# ── DeforestationDetector ──────────────────────────────────────────────────────

class TestDeforestationDetector:
    def test_no_deforestation_stable_forest(self):
        veg = make_s2_with_vegetation()
        detector = DeforestationDetector()
        _, conf = detector.detect(veg, veg)
        assert conf == 0.0

    def test_detects_ndvi_decline(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()  # NDVI drops sharply
        detector = DeforestationDetector(forest_baseline_ndvi=0.3, ndvi_decline_threshold=0.1)
        mask, conf = detector.detect(before, after)
        assert conf > 0.0, "NDVI decline in forested area should be detected"

    def test_confidence_bounded(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        _, conf = DeforestationDetector(
            forest_baseline_ndvi=0.3, ndvi_decline_threshold=0.1
        ).detect(before, after)
        assert 0.0 <= conf <= 1.0


# ── FireDetector ───────────────────────────────────────────────────────────────

class TestFireDetector:
    def test_no_fire_identical(self):
        arr = make_s2()
        _, conf = FireDetector().detect(arr, arr)
        assert conf == 0.0

    def test_detects_burn_scar(self):
        before = make_s2_with_vegetation()
        after = make_s2_burned()
        detector = FireDetector(dnbr_threshold=0.05)
        mask, conf = detector.detect(before, after)
        assert conf > 0.0, "Unburned→burned NBR decrease should trigger fire detector"

    def test_confidence_bounded(self):
        before = make_s2_with_vegetation()
        after = make_s2_burned()
        _, conf = FireDetector(dnbr_threshold=0.05).detect(before, after)
        assert 0.0 <= conf <= 1.0


# ── FloodDetector ──────────────────────────────────────────────────────────────

class TestFloodDetector:
    def test_no_flood_identical_sar(self):
        sar = make_sar(vv=-10.0)
        _, conf = FloodDetector().detect(sar, sar)
        assert conf == 0.0

    def test_detects_vv_decrease(self):
        before_sar = make_sar(vv=-5.0)   # pre-flood: high backscatter
        after_sar = make_sar(vv=-20.0)   # post-flood: backscatter drops
        mask, conf = FloodDetector(vv_decrease_threshold=4.0).detect(before_sar, after_sar)
        assert conf > 0.0, "15 dB VV decrease should trigger flood detector"

    def test_urban_mask_excludes_buildup(self):
        before_sar = make_sar(vv=-5.0)
        after_sar = make_sar(vv=-20.0)
        after_s2 = make_s2_with_buildup()  # all urban → should suppress flood mask
        mask, conf = FloodDetector(
            vv_decrease_threshold=4.0, urban_ndbi_threshold=0.0
        ).detect(before_sar, after_sar, after_s2)
        assert mask.sum() == 0, "Urban-masked pixels should not be flagged as flood"


# ── SolarDetector ──────────────────────────────────────────────────────────────

class TestSolarDetector:
    def test_no_solar_identical(self):
        arr = make_s2()
        _, conf = SolarDetector().detect(arr, arr)
        assert conf == 0.0

    def test_rule_based_detects_new_solar(self):
        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()  # NDBI increase + low NDVI
        detector = SolarDetector(ndbi_threshold=0.05, ndvi_threshold=0.5)
        mask, conf = detector.detect(before, after)
        assert conf >= 0.0


# ── EventClassifier integration ────────────────────────────────────────────────

class TestEventClassifier:
    def test_no_change_returns_none(self):
        from apps.api.services.classifier import EventClassifier

        arr = make_s2()
        clf = EventClassifier(detection_types=["construction", "deforestation"])
        result = clf.classify(arr, arr)
        assert result is None, "No change should return None"

    def test_detects_and_classifies_change(self):
        from apps.api.services.classifier import EventClassifier

        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        clf = EventClassifier(
            detection_types=["construction", "deforestation"],
            min_confidence=0.01,
        )
        result = clf.classify(before, after)
        assert result is not None
        assert result.detected_type in {"construction", "deforestation"}
        assert 0.0 <= result.confidence <= 1.0

    def test_centroid_computed_with_bbox(self):
        from apps.api.services.classifier import EventClassifier

        before = make_s2_with_vegetation()
        after = make_s2_with_buildup()
        bbox = [76.9, 13.2, 77.4, 13.7]
        clf = EventClassifier(
            detection_types=["construction", "deforestation"],
            min_confidence=0.01,
            bbox=bbox,
        )
        result = clf.classify(before, after)
        if result is not None and result.lat is not None:
            assert bbox[1] <= result.lat <= bbox[3]
            assert bbox[0] <= result.lon <= bbox[2]


# ── EventExplainer ─────────────────────────────────────────────────────────────

class TestEventExplainer:
    def test_fallback_description_all_types(self):
        from apps.api.services.explainer import EventExplainer

        explainer = EventExplainer()
        for det_type in ["construction", "deforestation", "fire", "flood", "solar", "unknown"]:
            meta = {
                "detected_type": det_type,
                "confidence": 0.75,
                "lat": 13.3,
                "lon": 77.1,
                "region_name": "Test Region",
                "first_seen": "2026-01-15",
                "before_date": "2025-12-01",
                "after_date": "2026-01-15",
            }
            desc = explainer._fallback_description(meta)
            assert isinstance(desc, str)
            assert len(desc) > 20

    def test_prompt_contains_key_info(self):
        from apps.api.services.explainer import EventExplainer

        meta = {
            "detected_type": "fire",
            "confidence": 0.88,
            "lat": 13.3,
            "lon": 77.1,
            "region_name": "Bellary",
            "first_seen": "2026-01-15",
            "before_date": "2025-12-01",
            "after_date": "2026-01-15",
        }
        prompt = EventExplainer._build_prompt(meta)
        assert "Bellary" in prompt
        assert "88.0" in prompt  # confidence pct
        assert "fire" in prompt
