from __future__ import annotations

import pytest

from backend.business.account import AccountSnapshot, PositionSnapshot
from backend.infra.integrations.mx_agent_tools import TradeTool


class FakePortfolio:
    async def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            total_asset=100_000,
            available_cash=250_000,
            frozen_cash=0,
            market_value=75_000,
            total_profit=0,
            daily_profit=0,
        )

    async def get_positions(self) -> list[object]:
        return []

    async def get_orders(self) -> list[object]:
        return []


class FakeTrading:
    async def trade(self, instruction: str) -> dict[str, object]:
        return {
            "status": "submitted",
            "data": {
                "stockCode": "600519",
                "stockName": "贵州茅台",
                "filledQuantity": 100,
                "filledPrice": 1700,
            },
        }


class FakeTradingResult(FakeTrading):
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result

    async def trade(self, instruction: str) -> dict[str, object]:
        del instruction
        return self.result


class RecordingNotifier:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def notify(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return True


@pytest.mark.asyncio
async def test_trade_tool_notifies_after_successful_trade() -> None:
    notifier = RecordingNotifier()
    result = await TradeTool(
        FakeTrading(),
        FakePortfolio(),
        notifier=notifier,  # type: ignore[arg-type]
    ).run("买入 600519 1700 100")

    assert result["status"] == "submitted"
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["intent"].payload["stockCode"] == "600519"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_trade_tool_keeps_trade_success_when_notification_fails() -> None:
    notifier = RecordingNotifier(RuntimeError("push failed"))

    result = await TradeTool(
        FakeTrading(),
        FakePortfolio(),
        notifier=notifier,  # type: ignore[arg-type]
    ).run("买入 600519 1700 100")

    assert result["status"] == "submitted"


@pytest.mark.asyncio
async def test_trade_tool_does_not_notify_when_preflight_blocks_trade() -> None:
    notifier = RecordingNotifier()

    with pytest.raises(ValueError, match="超过当前可用资金"):
        await TradeTool(
            FakeTrading(),
            FakePortfolioWithCash(available_cash=1),
            notifier=notifier,  # type: ignore[arg-type]
        ).run("买入 600519 1700 100")

    assert notifier.calls == []


class FakePortfolioWithCash(FakePortfolio):
    def __init__(self, *, available_cash: float) -> None:
        self.available_cash = available_cash

    async def get_account_snapshot(self) -> AccountSnapshot:
        snapshot = await super().get_account_snapshot()
        return AccountSnapshot(
            total_asset=snapshot.total_asset,
            available_cash=self.available_cash,
            frozen_cash=snapshot.frozen_cash,
            market_value=snapshot.market_value,
            total_profit=snapshot.total_profit,
            daily_profit=snapshot.daily_profit,
        )


class FakePortfolioWithPosition(FakePortfolio):
    async def get_positions(self) -> list[PositionSnapshot]:
        return [
            PositionSnapshot(
                symbol="600519",
                stock_name="贵州茅台",
                quantity=200,
                avg_cost=1600,
                current_price=1700,
                market_value=340_000,
                profit_ratio=0.0625,
                available_quantity=200,
            )
        ]


@pytest.mark.asyncio
async def test_trade_tool_notifies_successful_sell_with_executed_values() -> None:
    notifier = RecordingNotifier()
    result = await TradeTool(
        FakeTradingResult(
            {
                "status": "submitted",
                "data": {
                    "stockCode": "600519",
                    "stockName": "贵州茅台",
                    "filledQuantity": 120,
                    "filledPrice": 1688.5,
                },
            }
        ),
        FakePortfolioWithPosition(),
        notifier=notifier,  # type: ignore[arg-type]
    ).run("卖出 600519 1700 200")

    assert result["status"] == "submitted"
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["intent"].payload["type"] == "sell"  # type: ignore[union-attr]
    assert notifier.calls[0]["result"]["data"]["filledQuantity"] == 120  # type: ignore[index]


@pytest.mark.asyncio
async def test_trade_tool_does_not_notify_failed_trade_response() -> None:
    notifier = RecordingNotifier()

    result = await TradeTool(
        FakeTradingResult({"status": "failed", "message": "rejected"}),
        FakePortfolio(),
        notifier=notifier,  # type: ignore[arg-type]
    ).run("买入 600519 1700 100")

    assert result["status"] == "failed"
    assert notifier.calls == []
