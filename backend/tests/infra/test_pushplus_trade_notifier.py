from __future__ import annotations

import pytest

from backend.business.settings import AppSettings, PushplusChannel, PushplusSettings
from backend.infra.integrations.pushplus import PushplusTradeNotifier
from backend.infra.repositories import SettingsRepository
from backend.stock_api.mx.trading_parser import parse_trade_instruction


class FakePushplusSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def send(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"code": 200}


async def save_settings(session_factory, settings: AppSettings) -> None:
    async with session_factory() as session:
        await SettingsRepository(session).save(settings)
        await session.commit()


@pytest.mark.asyncio
async def test_disabled_pushplus_skips_trade_notification(session_factory) -> None:
    await save_settings(session_factory, AppSettings(pushplus_token="secret-token"))
    sender = FakePushplusSender()
    notifier = PushplusTradeNotifier(session_factory=session_factory, client=sender)  # type: ignore[arg-type]

    sent = await notifier.notify(
        result={"data": {"stockName": "贵州茅台"}},
        intent=parse_trade_instruction("买入 600519 1700 100"),
    )

    assert sent is False
    assert sender.calls == []


@pytest.mark.asyncio
async def test_enabled_pushplus_sends_latest_trade_summary(session_factory) -> None:
    await save_settings(
        session_factory,
        AppSettings(
            pushplus=PushplusSettings(
                enabled=True,
                channel=PushplusChannel.CMCC,
            ),
            pushplus_token="secret-token",
        ),
    )
    sender = FakePushplusSender()
    notifier = PushplusTradeNotifier(session_factory=session_factory, client=sender)  # type: ignore[arg-type]

    sent = await notifier.notify(
        result={
            "data": {
                "stockName": "贵州茅台",
                "filledQuantity": 100,
                "filledPrice": 1700,
            }
        },
        intent=parse_trade_instruction("买入 600519 1700 100"),
    )

    assert sent is True
    assert sender.calls[0]["token"] == "secret-token"
    assert sender.calls[0]["channel"] is PushplusChannel.CMCC
    assert "贵州茅台" in str(sender.calls[0]["content"])
    assert "170000.00" in str(sender.calls[0]["content"])


@pytest.mark.asyncio
async def test_pushplus_failure_is_logged_without_token_leak(session_factory) -> None:
    await save_settings(
        session_factory,
        AppSettings(
            pushplus=PushplusSettings(enabled=True),
            pushplus_token="secret-token",
        ),
    )
    sender = FakePushplusSender(RuntimeError("secret-token upstream failed"))
    messages: list[str] = []

    def error_logger(*args: object) -> None:
        messages.append(" ".join(str(arg) for arg in args))

    notifier = PushplusTradeNotifier(
        session_factory=session_factory,
        client=sender,  # type: ignore[arg-type]
        error_logger=error_logger,
    )

    sent = await notifier.notify(
        result={},
        intent=parse_trade_instruction("卖出 600519 1700 100"),
    )

    assert sent is False
    assert messages
    assert "secret-token" not in " ".join(messages)
