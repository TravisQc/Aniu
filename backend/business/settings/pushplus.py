"""PushPlus notification settings value objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from backend.business.settings.prompt import normalize_optional_str


class PushplusChannel(StrEnum):
    """PushPlus channels supported by the application."""

    WECHAT = "wechat"
    WEBHOOK = "webhook"
    CMCC = "cmcc"


@dataclass(frozen=True, slots=True)
class PushplusSettings:
    """Non-secret PushPlus delivery configuration."""

    enabled: bool = False
    channel: PushplusChannel = PushplusChannel.WECHAT
    webhook_option: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("pushplus.enabled must be a boolean")
        try:
            channel = PushplusChannel(self.channel)
        except ValueError as exc:
            raise ValueError(
                "pushplus.channel must be one of: wechat, webhook, cmcc"
            ) from exc
        option = normalize_optional_str(self.webhook_option)
        if channel is PushplusChannel.WEBHOOK and option is None:
            raise ValueError("pushplus.webhook_option is required for webhook")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "webhook_option", option)

    @classmethod
    def from_mapping(cls, value: object | None) -> PushplusSettings:
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("pushplus settings must be an object")
        return cls(
            enabled=value.get("enabled", False),
            channel=value.get("channel", PushplusChannel.WECHAT),
            webhook_option=value.get("webhook_option"),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "channel": self.channel.value,
            "webhook_option": self.webhook_option,
        }


__all__ = ["PushplusChannel", "PushplusSettings"]
