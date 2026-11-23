"""Watchlist table projection tolerates missing metadata without losing stocks."""

from __future__ import annotations

import pytest

from backend.business.account.watchlist import WatchlistService
from backend.business.shared import ServiceIntegrationError


class FakeWatchlistClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def query(self) -> dict[str, object]:
        return self.payload


@pytest.mark.asyncio
async def test_watchlist_infers_missing_columns_and_keeps_codes_and_nulls() -> None:
    service = WatchlistService(
        FakeWatchlistClient(
            {
                "data": {
                    "allResults": {
                        "result": {
                            "dataList": [
                                {
                                    "SECURITY_CODE": "000001",
                                    "SECURITY_NAME": "平安银行",
                                },
                                {"SECURITY_CODE": "600519", "最新价": 1500.5},
                            ]
                        }
                    }
                }
            }
        )
    )
    watchlist = await service.get_watchlist()
    assert [(column.key, column.title) for column in watchlist.columns] == [
        ("SECURITY_CODE", "股票代码"),
        ("SECURITY_NAME", "股票名称"),
        ("最新价", "最新价"),
    ]
    assert watchlist.items == [
        {"SECURITY_CODE": "000001", "SECURITY_NAME": "平安银行", "最新价": None},
        {"SECURITY_CODE": "600519", "SECURITY_NAME": None, "最新价": "1500.5"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", [{}, None, {"allResults": {"result": {"dataList": []}}}]
)
async def test_watchlist_handles_empty_accounts(data: object) -> None:
    watchlist = await WatchlistService(
        FakeWatchlistClient({"data": data})
    ).get_watchlist()
    assert watchlist.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", [{"unexpected": []}, {"dataList": "invalid"}, {"dataList": [1]}]
)
async def test_watchlist_rejects_malformed_data_instead_of_hiding_stocks(
    data: object,
) -> None:
    with pytest.raises(ServiceIntegrationError, match="自选股列表返回格式异常"):
        await WatchlistService(FakeWatchlistClient({"data": data})).get_watchlist()
