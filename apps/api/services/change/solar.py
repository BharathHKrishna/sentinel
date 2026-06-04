"""
Solar farm change detector.

Two operating modes:
  1. CNN mode  — loads a fine-tuned MobileNetV3-small from
                 `models/solar_current.pt` and runs patch-wise inference.
  2. Rule-based fallback — uses high NDBI + low NDVI signature of
                 large-scale solar panels (reflective, non-vegetated surfaces).

The rule-based approach exploits the fact that solar panels have:
  - Moderate-to-high SWIR reflectance → positive NDBI
  - Very low red reflectance → very negative NDVI (dark surfaces in visible)
  - Characteristic blue/green ratio unlike bare soil
"""
import logging
import os
from pathlib import Path
from typing import Tuple

import numpy as np

from apps.api.services.change.generic import compute_ndbi, compute_ndvi

logger = logging.getLogger(__name__)

MODEL_PATH = Path("models/solar_current.pt")


def _load_cnn_model():
    """Load fine-tuned MobileNetV3-small if available, else return None."""
    if not MODEL_PATH.exists():
        return None
    try:
        import torch
        import torchvision.models as models

        model = models.mobilenet_v3_small(weights=None)
        # Replace classifier head: 2 classes (solar / no-solar)
        in_features = model.classifier[-1].in_features
        import torch.nn as nn
        model.classifier[-1] = nn.Linear(in_features, 2)
        state = torch.load(MODEL_PATH, map_location="cpu")
        model.load_state_dict(state)
        model.eval()
        logger.info("Loaded solar CNN model from %s", MODEL_PATH)
        return model
    except Exception as exc:
        logger.warning("Could not load solar model: %s — falling back to rule-based", exc)
        return None


_CNN_MODEL = None
_CNN_LOADED = False


def _get_model():
    global _CNN_MODEL, _CNN_LOADED
    if not _CNN_LOADED:
        _CNN_MODEL = _load_cnn_model()
        _CNN_LOADED = True
    return _CNN_MODEL


def _rule_based_detect(
    before: np.ndarray,
    after: np.ndarray,
    ndbi_threshold: float,
    ndvi_threshold: float,
) -> Tuple[np.ndarray, float]:
    """
    Flag pixels where NDBI increased AND NDVI is now very low —
    characteristic of newly installed solar farms on previously vegetated
    or bare land.
    """
    ndbi_before = compute_ndbi(before)
    ndbi_after = compute_ndbi(after)
    ndvi_after = compute_ndvi(after)

    ndbi_delta = ndbi_after - ndbi_before

    # Solar farms: reflective panels → NDBI increases + NDVI drops below threshold
    mask = (ndbi_delta >= ndbi_threshold) & (ndvi_after <= ndvi_threshold)

    if mask.sum() == 0:
        return mask, 0.0

    mean_delta = float(ndbi_delta[mask].mean())
    confidence = float(np.clip(mean_delta / 0.4, 0.0, 1.0))
    return mask, confidence


def _cnn_detect(
    model,
    before: np.ndarray,
    after: np.ndarray,
    patch_size: int = 64,
    stride: int = 32,
) -> Tuple[np.ndarray, float]:
    """
    Run CNN patch-wise over the after image.  Returns a confidence map.
    Uses RGB bands (B02, B03, B04) from the after composite.
    """
    import torch

    h, w = after.shape[:2]
    confidence_map = np.zeros((h, w), dtype=np.float32)
    count_map = np.zeros((h, w), dtype=np.int32)

    # Extract RGB (B02=1, B03=2, B04=3)
    rgb_after = after[:, :, [1, 2, 3]]  # (H, W, 3)
    rgb_before = before[:, :, [1, 2, 3]]
    # Stack as 6-channel difference input
    diff = np.concatenate(
        [rgb_after - rgb_before, rgb_after], axis=2
    )  # (H, W, 6)

    # Pad to fit patch_size
    pad_h = (patch_size - h % patch_size) % patch_size
    pad_w = (patch_size - w % patch_size) % patch_size
    diff_padded = np.pad(diff, ((0, pad_h), (0, pad_w), (0, 0)))

    hp, wp = diff_padded.shape[:2]

    # Adapt first conv if needed (expects 3 channels, we pass 6 — slice to 3)
    input_data = diff_padded[:, :, :3]  # use difference channels only

    for y in range(0, hp - patch_size + 1, stride):
        for x in range(0, wp - patch_size + 1, stride):
            patch = input_data[y : y + patch_size, x : x + patch_size, :]
            # (3, H, W) tensor, normalised
            tensor = torch.from_numpy(patch.transpose(2, 0, 1)).float().unsqueeze(0)
            tensor = (tensor - 0.5) / 0.5
            with torch.no_grad():
                logits = model(tensor)
                prob = torch.softmax(logits, dim=1)[0, 1].item()  # solar class

            cy = min(y + patch_size, h)
            cx = min(x + patch_size, w)
            confidence_map[y:cy, x:cx] += prob
            count_map[y:cy, x:cx] += 1

    count_map = np.maximum(count_map, 1)
    confidence_map /= count_map

    mask = confidence_map >= 0.5
    if mask.sum() == 0:
        return mask, 0.0

    confidence = float(confidence_map[mask].mean())
    return mask, confidence


class SolarDetector:
    """
    Detects new solar farm installation.

    Uses a CNN if `models/solar_current.pt` exists, otherwise falls back
    to NDBI + NDVI rule-based detection.
    """

    def __init__(
        self,
        ndbi_threshold: float = 0.1,
        ndvi_threshold: float = 0.15,
    ) -> None:
        self.ndbi_threshold = ndbi_threshold
        self.ndvi_threshold = ndvi_threshold

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
        model = _get_model()
        if model is not None:
            try:
                return _cnn_detect(model, before, after)
            except Exception as exc:
                logger.warning("CNN inference failed: %s — using rule-based fallback", exc)

        return _rule_based_detect(before, after, self.ndbi_threshold, self.ndvi_threshold)
