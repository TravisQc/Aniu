"""Sector-flow fallback contracts and source-specific normalization."""

from __future__ import annotations

import httpx
import pytest

from backend.infra.integrations.public_stock_agent_tools import StockMoneyFlowTool
from backend.stock_api.models import StockApiCall
from backend.stock_api.public.contracts import SectorMoneyFlowRequest
from backend.stock_api.public.errors import NoStockData, UpstreamUnavailable
from backend.stock_api.public.http import PublicHttpTransport
from backend.stock_api.public.normalizers.market import normalize_sina_sector_money_flow
from backend.stock_api.public.providers.eastmoney import EastMoneyAdapter
from backend.stock_api.public.providers.sina import SinaAdapter
from backend.stock_api.public.providers.tencent import TencentAdapter
from backend.stock_api.public.router import PublicProviderAdapters, PublicStockRouter
from backend.stock_api.public.service import StockMarketDataService


def sina_rows() -> list[dict[str, str]]:
    return [
        {
            "category": f"sector-{index}",
            "name": f"板块{index}",
            "avg_price": "10.5",
            "avg_changeratio": "-0.0125",
            "netamount": str(100_000_000.25 - index * 1_000_000),
        }
        for index in range(20)
    ]


def build_service(
    handler,
    logs: list[StockApiCall] | None = None,
) -> StockMarketDataService:
    async def record(call: StockApiCall) -> None:
        if logs is not None:
            logs.append(call)

    transport = PublicHttpTransport(
        transport=httpx.MockTransport(handler), call_logger=record
    )
    for gate in transport._gates.values():
        gate.minimum_start_interval = 0
    router = PublicStockRouter(
        PublicProviderAdapters(
            eastmoney=EastMoneyAdapter(transport),
            sina=SinaAdapter(transport),
            tencent=TencentAdapter(transport),
        )
    )
    return StockMarketDataService(router, transport=transport)


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [1, 2])
@pytest.mark.parametrize(
    ("sector_type", "fenlei"), [("industry", "0"), ("concept", "1")]
)
async def test_sector_flow_recovers_after_both_eastmoney_hosts_disconnect(
    page: int,
    sector_type: str,
    fenlei: str,
) -> None:
    seen: list[httpx.Request] = []
    logs: list[StockApiCall] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host.endswith("eastmoney.com"):
            raise httpx.RemoteProtocolError("Server disconnected", request=request)
        assert request.url.host == "vip.stock.finance.sina.com.cn"
        assert request.url.path.endswith("MoneyFlow.ssl_bkzj_bk")
        assert dict(request.url.params) == {
            "fenlei": fenlei,
            "page": str(page),
            "num": "6",
            "sort": "netamount",
            "asc": "0",
        }
        start = (page - 1) * 6
        return httpx.Response(200, json=sina_rows()[start : start + 6])

    service = build_service(handler, logs)
    try:
        result = await StockMoneyFlowTool(service).run(
            action="sector", sector_type=sector_type, page=page, limit=6
        )
    finally:
        await service.aclose()
    data, meta = result["data"], result["meta"]
    start = (page - 1) * 6
    assert data["page"] == page
    assert data["sector_type"] == sector_type
    assert data["limit"] == 6
    assert [item["id"] for item in data["items"]] == [
        f"sector-{index}" for index in range(start, start + 6)
    ]
    assert data["items"][0]["net_inflow"] == 100_000_000.25 - start * 1_000_000
    assert data["items"][0]["change_percent"] == -1.25
    assert data["items"][0]["price"] == 10.5
    assert data["items"][0]["amount"] is None
    assert meta["source"] == "sina"
    assert meta["attempted_sources"] == ["eastmoney", "sina"]
    assert meta["fallback_used"] is True
    assert meta["degraded"] is True
    assert any(
        "分类" in warning and "统计口径" in warning for warning in meta["warnings"]
    )
    assert [request.url.host for request in seen] == [
        "push2.eastmoney.com",
        "push2delay.eastmoney.com",
        "vip.stock.finance.sina.com.cn",
    ]
    assert [call.error_category for call in logs] == ["network", "network", None]
    assert all(call.operation_id == "money_flow.sector" for call in logs)


@pytest.mark.asyncio
async def test_industry_flow_keeps_eastmoney_as_primary() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "rc": 0,
                "data": {"diff": [{"f12": "BK0001", "f14": "行业", "f62": 123}]},
            },
        )

    service = build_service(handler)
    try:
        result = await service.execute(SectorMoneyFlowRequest(limit=6))
    finally:
        await service.aclose()
    assert len(seen) == 1
    assert result["meta"]["source"] == "eastmoney"
    assert result["meta"]["fallback_used"] is False
    assert result["meta"]["degraded"] is False
    assert result["data"]["items"][0]["net_inflow"] == 123


@pytest.mark.asyncio
async def test_industry_flow_falls_back_when_eastmoney_returns_no_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.endswith("eastmoney.com"):
            return httpx.Response(200, json={"rc": 0, "data": {"diff": []}})
        return httpx.Response(200, json=sina_rows())

    service = build_service(handler)
    try:
        result = await service.execute(SectorMoneyFlowRequest(limit=6))
    finally:
        await service.aclose()
    assert result["meta"]["source"] == "sina"
    assert result["meta"]["fallback_used"] is True
    assert len(result["data"]["items"]) == 6


@pytest.mark.parametrize(
    "flow_request",
    [
        SectorMoneyFlowRequest(sector_type="concept", limit=6),
        SectorMoneyFlowRequest(limit=21),
        SectorMoneyFlowRequest(page=4, limit=6),
    ],
)
def test_sina_fallback_supports_sector_types_and_larger_pages(
    flow_request: SectorMoneyFlowRequest,
) -> None:
    transport = PublicHttpTransport(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    )
    router = PublicStockRouter(
        PublicProviderAdapters(
            eastmoney=EastMoneyAdapter(transport),
            sina=SinaAdapter(transport),
            tencent=TencentAdapter(transport),
        )
    )
    assert [
        candidate.provider for candidate in router.candidates_for(flow_request)
    ] == ["eastmoney", "sina"]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"__ERROR": 1, "__ERRORMSG": "Input error"}, UpstreamUnavailable),
        (
            [{"category": "new_jxhy", "name": "机械行业", "avg_price": "10"}],
            UpstreamUnavailable,
        ),
        ([], NoStockData),
    ],
)
def test_invalid_sina_response_cannot_be_reported_as_money_flow_success(
    payload: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        normalize_sina_sector_money_flow(payload, SectorMoneyFlowRequest(limit=6))
