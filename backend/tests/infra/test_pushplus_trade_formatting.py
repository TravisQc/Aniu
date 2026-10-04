from __future__ import annotations

from backend.infra.integrations.pushplus import (
    format_trade_notification,
    normalize_trade_notification,
)
from backend.stock_api.mx.trading_parser import parse_trade_instruction


def test_normalize_buy_trade_from_nested_response_and_format_amount() -> None:
    intent = parse_trade_instruction("买入 600519 1700 100")
    trade = normalize_trade_notification(
        {
            "code": 200,
            "data": {
                "stockCode": "600519",
                "stockName": "贵州茅台",
                "filledQuantity": 100,
                "filledPrice": 1699.5,
            },
        },
        intent,
    )

    assert trade.stock_name == "贵州茅台"
    assert trade.stock_code == "600519"
    assert trade.direction == "buy"
    assert trade.quantity == 100
    assert trade.total_amount == 169950.0
    assert "交易方向：买入" in format_trade_notification(trade)
    assert "交易总额：169950.00 元" in format_trade_notification(trade)


def test_normalize_sell_trade_uses_result_fields_and_fallback_name() -> None:
    intent = parse_trade_instruction("卖出 600519 1700 200")
    trade = normalize_trade_notification(
        {"result": {"quantity": 200, "price": 1688}},
        intent,
        fallback_stock_name="贵州茅台",
    )

    assert trade.stock_name == "贵州茅台"
    assert trade.direction == "sell"
    assert trade.quantity == 200
    assert trade.price == 1688
    assert trade.total_amount == 337600
    assert "交易方向：卖出" in format_trade_notification(trade)


def test_normalize_trade_falls_back_to_instruction_when_response_is_sparse() -> None:
    intent = parse_trade_instruction("买入 600519 1700 100")
    trade = normalize_trade_notification({}, intent)

    assert trade.stock_name == "600519"
    assert trade.stock_code == "600519"
    assert trade.quantity == 100
    assert trade.price == 1700
