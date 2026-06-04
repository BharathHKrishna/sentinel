"""
EventExplainer

Generates a concise, human-readable description of a detected satellite
anomaly using the Groq API (Llama 3.3-70B).
"""
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


class EventExplainer:
    """
    Calls Groq's chat completions endpoint to produce a 2-3 sentence plain-
    English description of a detected change event.
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set — explanations will be empty")

    def explain(self, event_metadata: Dict[str, Any]) -> Optional[str]:
        """
        Parameters
        ----------
        event_metadata : dict with keys:
            detected_type, confidence, lat, lon, region_name,
            first_seen (ISO string), before_date, after_date

        Returns
        -------
        A 2-3 sentence description string, or None on failure.
        """
        if not self.api_key:
            return self._fallback_description(event_metadata)

        prompt = self._build_prompt(event_metadata)

        try:
            resp = httpx.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a satellite imagery analyst assistant. "
                                "Write clear, factual, concise descriptions of detected "
                                "land-use changes for a general audience. "
                                "Use exactly 2-3 sentences. Do not speculate beyond the data."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            logger.debug("Groq explanation: %s", text)
            return text

        except httpx.HTTPStatusError as exc:
            logger.error("Groq API HTTP error: %s — %s", exc.response.status_code, exc.response.text)
            return self._fallback_description(event_metadata)
        except Exception as exc:
            logger.error("Groq API call failed: %s", exc)
            return self._fallback_description(event_metadata)

    @staticmethod
    def _build_prompt(meta: Dict[str, Any]) -> str:
        det_type = meta.get("detected_type", "unknown")
        confidence_pct = round(float(meta.get("confidence", 0)) * 100, 1)
        region = meta.get("region_name", "the monitored region")
        lat = meta.get("lat")
        lon = meta.get("lon")
        before_date = meta.get("before_date", "the previous observation")
        after_date = meta.get("after_date", "the latest observation")

        location_str = f"at approximately {lat:.4f}°N, {lon:.4f}°E" if lat and lon else f"in {region}"

        type_context = {
            "construction": "new construction or land clearing for development",
            "deforestation": "forest clearing or vegetation loss",
            "fire": "fire damage or burn scarring",
            "flood": "surface water inundation or flooding",
            "solar": "installation of a new solar farm",
        }.get(det_type, det_type)

        return (
            f"Satellite analysis detected {type_context} {location_str} in the region "
            f"'{region}'. The change was identified between imagery from {before_date} and "
            f"{after_date}, with a detection confidence of {confidence_pct}%. "
            f"Please write a 2-3 sentence factual description of what this likely means "
            f"on the ground, appropriate for a non-expert reader."
        )

    @staticmethod
    def _fallback_description(meta: Dict[str, Any]) -> str:
        """Return a template-based description when the LLM is unavailable."""
        det_type = meta.get("detected_type", "change")
        region = meta.get("region_name", "the monitored region")
        confidence_pct = round(float(meta.get("confidence", 0)) * 100, 1)
        after_date = meta.get("after_date", "the latest observation")

        descriptions = {
            "construction": (
                f"Satellite imagery from {after_date} shows signs of new construction "
                f"activity in {region}. Increased built-up surface reflectance was "
                f"detected with {confidence_pct}% confidence."
            ),
            "deforestation": (
                f"A significant reduction in vegetation cover was detected in {region} "
                f"as of {after_date}. The NDVI decline is consistent with forest clearing "
                f"or agricultural land conversion ({confidence_pct}% confidence)."
            ),
            "fire": (
                f"Burn scarring consistent with recent fire activity was detected in "
                f"{region} ({after_date}). The dNBR signal indicates moderate-to-high "
                f"burn severity ({confidence_pct}% confidence)."
            ),
            "flood": (
                f"Surface water inundation was detected in {region} as of {after_date}, "
                f"based on reduced SAR backscatter in the VV polarisation channel "
                f"({confidence_pct}% confidence)."
            ),
            "solar": (
                f"Imagery from {after_date} indicates a new large-scale solar installation "
                f"in {region}. The spectral signature is consistent with photovoltaic panel "
                f"arrays ({confidence_pct}% confidence)."
            ),
        }
        return descriptions.get(
            det_type,
            f"A land-use change of type '{det_type}' was detected in {region} "
            f"({confidence_pct}% confidence).",
        )
