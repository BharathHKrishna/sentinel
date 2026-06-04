"""
AlertNotifier

Sends event alerts via SendGrid (email) and Slack webhooks.
"""
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL", "alerts@sentinel.app")
SENDGRID_FROM_NAME = "Sentinel Alerts"


class AlertNotifier:
    """Dispatches event notifications over email (SendGrid) and Slack."""

    def __init__(self) -> None:
        self.sendgrid_api_key = os.environ.get("SENDGRID_API_KEY", "")
        self.default_slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    # ── Email (SendGrid) ────────────────────────────────────────────────────

    def send_email(self, to: str, event: Dict[str, Any]) -> bool:
        """
        Send an event alert email via SendGrid.

        Parameters
        ----------
        to    : recipient email address
        event : dict with event fields (id, detected_type, confidence,
                lat, lon, region_name, description, first_seen,
                before_tile_url, after_tile_url)

        Returns
        -------
        True on success, False on failure.
        """
        if not self.sendgrid_api_key:
            logger.warning("SENDGRID_API_KEY not set — skipping email to %s", to)
            return False

        subject = self._email_subject(event)
        html_body = self._email_html(event)
        text_body = self._email_text(event)

        payload = {
            "personalizations": [
                {
                    "to": [{"email": to}],
                    "subject": subject,
                }
            ],
            "from": {
                "email": SENDGRID_FROM_EMAIL,
                "name": SENDGRID_FROM_NAME,
            },
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }

        try:
            resp = httpx.post(
                SENDGRID_API_URL,
                headers={
                    "Authorization": f"Bearer {self.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            logger.info("Email sent to %s (event id=%s)", to, event.get("id"))
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SendGrid error %s: %s", exc.response.status_code, exc.response.text[:200]
            )
            return False
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            return False

    @staticmethod
    def _email_subject(event: Dict[str, Any]) -> str:
        region = event.get("region_name", "Unknown Region")
        det_type = event.get("detected_type", "change").replace("_", " ").title()
        return f"[Sentinel Alert] {det_type} detected in {region}"

    @staticmethod
    def _email_text(event: Dict[str, Any]) -> str:
        return (
            f"Sentinel has detected a change in {event.get('region_name', 'your monitored region')}.\n\n"
            f"Type        : {event.get('detected_type', 'N/A')}\n"
            f"Confidence  : {round(float(event.get('confidence', 0)) * 100, 1)}%\n"
            f"Location    : {event.get('lat', 'N/A')}, {event.get('lon', 'N/A')}\n"
            f"Detected at : {event.get('first_seen', 'N/A')}\n\n"
            f"Description:\n{event.get('description', 'No description available.')}\n\n"
            f"View event: https://sentinel.app/events/{event.get('id')}\n"
        )

    @staticmethod
    def _email_html(event: Dict[str, Any]) -> str:
        region = event.get("region_name", "Unknown Region")
        det_type = event.get("detected_type", "N/A").replace("_", " ").title()
        confidence_pct = round(float(event.get("confidence", 0)) * 100, 1)
        lat = event.get("lat", "N/A")
        lon = event.get("lon", "N/A")
        first_seen = event.get("first_seen", "N/A")
        description = event.get("description", "No description available.")
        event_id = event.get("id", "")
        before_url = event.get("before_tile_url", "")
        after_url = event.get("after_tile_url", "")

        tile_html = ""
        if before_url and after_url:
            tile_html = f"""
            <tr>
              <td colspan="2" style="padding:12px 0;">
                <table width="100%" cellspacing="8"><tr>
                  <td width="50%"><strong>Before</strong><br>
                    <img src="{before_url}" width="100%" style="border-radius:4px;">
                  </td>
                  <td width="50%"><strong>After</strong><br>
                    <img src="{after_url}" width="100%" style="border-radius:4px;">
                  </td>
                </tr></table>
              </td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">
<table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;
  padding:24px;margin:auto;">
  <tr>
    <td colspan="2">
      <h2 style="color:#e53e3e;margin:0 0 16px;">
        🛰️ Sentinel Alert — {det_type}
      </h2>
    </td>
  </tr>
  <tr>
    <td style="padding:4px 0;color:#555;">Region</td>
    <td style="padding:4px 0;font-weight:bold;">{region}</td>
  </tr>
  <tr>
    <td style="padding:4px 0;color:#555;">Detection Type</td>
    <td style="padding:4px 0;">{det_type}</td>
  </tr>
  <tr>
    <td style="padding:4px 0;color:#555;">Confidence</td>
    <td style="padding:4px 0;">{confidence_pct}%</td>
  </tr>
  <tr>
    <td style="padding:4px 0;color:#555;">Location</td>
    <td style="padding:4px 0;">{lat}, {lon}</td>
  </tr>
  <tr>
    <td style="padding:4px 0;color:#555;">Detected At</td>
    <td style="padding:4px 0;">{first_seen}</td>
  </tr>
  <tr>
    <td colspan="2" style="padding:16px 0 8px;">
      <p style="margin:0;color:#333;">{description}</p>
    </td>
  </tr>
  {tile_html}
  <tr>
    <td colspan="2" style="padding:16px 0 0;">
      <a href="https://sentinel.app/events/{event_id}"
         style="background:#3182ce;color:#fff;padding:10px 20px;
                border-radius:4px;text-decoration:none;">
        View Full Event →
      </a>
    </td>
  </tr>
</table>
</body></html>"""

    # ── Slack ───────────────────────────────────────────────────────────────

    def send_slack(self, webhook_url: str | None, event: Dict[str, Any]) -> bool:
        """
        Post an event alert to a Slack channel via Incoming Webhook.

        Parameters
        ----------
        webhook_url : Slack webhook URL (falls back to SLACK_WEBHOOK_URL env var)
        event       : same dict as send_email
        """
        url = webhook_url or self.default_slack_webhook
        if not url:
            logger.warning("No Slack webhook URL available — skipping notification")
            return False

        region = event.get("region_name", "Unknown Region")
        det_type = event.get("detected_type", "N/A").replace("_", " ").title()
        confidence_pct = round(float(event.get("confidence", 0)) * 100, 1)
        lat = event.get("lat", "N/A")
        lon = event.get("lon", "N/A")
        description = event.get("description", "")
        event_id = event.get("id", "")

        color_map = {
            "construction": "#f6ad55",
            "deforestation": "#68d391",
            "fire": "#fc8181",
            "flood": "#63b3ed",
            "solar": "#f6e05e",
        }
        color = color_map.get(event.get("detected_type", ""), "#a0aec0")

        payload = {
            "text": f":satellite: *Sentinel Alert* — {det_type} in *{region}*",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {"title": "Type", "value": det_type, "short": True},
                        {"title": "Confidence", "value": f"{confidence_pct}%", "short": True},
                        {"title": "Location", "value": f"{lat}, {lon}", "short": True},
                        {"title": "Region", "value": region, "short": True},
                    ],
                    "text": description or "No description available.",
                    "actions": [
                        {
                            "type": "button",
                            "text": "View Event",
                            "url": f"https://sentinel.app/events/{event_id}",
                        }
                    ],
                    "footer": "Sentinel Satellite Monitor",
                }
            ],
        }

        try:
            resp = httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Slack notification sent for event id=%s", event_id)
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Slack webhook error %s: %s", exc.response.status_code, exc.response.text[:200]
            )
            return False
        except Exception as exc:
            logger.error("Slack notification failed: %s", exc)
            return False
