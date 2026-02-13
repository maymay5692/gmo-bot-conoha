"""Tests for Discord webhook notification service."""
import json
from unittest.mock import patch, MagicMock

import pytest

from services.discord_notify import init_discord, send_alert


class TestInitDiscord:
    def test_init_with_url(self):
        init_discord("https://discord.com/api/webhooks/test/token")
        # Should not raise

    def test_init_with_none(self):
        init_discord(None)
        # Should not raise


class TestSendAlert:
    def setup_method(self):
        init_discord(None)

    def test_send_without_webhook_url_returns_false(self):
        init_discord(None)
        result = send_alert("Test", "message")
        assert result is False

    @patch("services.discord_notify.urllib.request.urlopen")
    def test_send_with_webhook_url_returns_true(self, mock_urlopen):
        init_discord("https://discord.com/api/webhooks/test/token")
        result = send_alert("Test Title", "Test message")
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("services.discord_notify.urllib.request.urlopen")
    def test_send_constructs_correct_payload(self, mock_urlopen):
        init_discord("https://discord.com/api/webhooks/test/token")
        send_alert("Alert Title", "Alert body", color=0x00FF00)

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))

        assert payload["embeds"][0]["title"] == "Alert Title"
        assert payload["embeds"][0]["description"] == "Alert body"
        assert payload["embeds"][0]["color"] == 0x00FF00

    @patch("services.discord_notify.urllib.request.urlopen")
    def test_send_default_color_is_red(self, mock_urlopen):
        init_discord("https://discord.com/api/webhooks/test/token")
        send_alert("Error", "Something failed")

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))

        assert payload["embeds"][0]["color"] == 0xFF0000

    @patch("services.discord_notify.urllib.request.urlopen", side_effect=Exception("Network error"))
    def test_send_handles_network_error_gracefully(self, mock_urlopen):
        init_discord("https://discord.com/api/webhooks/test/token")
        result = send_alert("Test", "message")
        assert result is False
