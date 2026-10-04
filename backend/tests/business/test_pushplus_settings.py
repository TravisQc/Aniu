from __future__ import annotations

import pytest

from backend.business.settings import PushplusChannel, PushplusSettings


def test_pushplus_settings_default_to_disabled_wechat() -> None:
    settings = PushplusSettings()

    assert settings.enabled is False
    assert settings.channel is PushplusChannel.WECHAT
    assert settings.webhook_option is None


def test_pushplus_settings_reject_unsupported_channel() -> None:
    with pytest.raises(ValueError, match="pushplus.channel"):
        PushplusSettings(channel="mail")


def test_pushplus_settings_require_webhook_option() -> None:
    with pytest.raises(ValueError, match="webhook_option"):
        PushplusSettings(channel=PushplusChannel.WEBHOOK)


def test_pushplus_settings_normalize_mapping_and_round_trip() -> None:
    settings = PushplusSettings.from_mapping(
        {"enabled": True, "channel": "webhook", "webhook_option": "  robot-code  "}
    )

    assert settings.as_dict() == {
        "enabled": True,
        "channel": "webhook",
        "webhook_option": "robot-code",
    }
