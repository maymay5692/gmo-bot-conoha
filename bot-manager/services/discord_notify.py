"""Discord Webhook notification service."""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = None


def init_discord(webhook_url):
    """Initialize Discord webhook URL."""
    global DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL = webhook_url


def send_alert(title, message, color=0xFF0000):
    """Send an alert to Discord via webhook.

    Args:
        title: Alert title
        message: Alert body
        color: Embed color (default: red)

    Returns:
        True if sent successfully, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook URL not configured, skipping alert")
        return False

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
        }]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        logger.warning("Discord notification failed: %s", e)
        return False
