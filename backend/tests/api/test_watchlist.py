"""Read-only watchlist API, runtime credentials and upstream error handling."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.business.settings import AppSettings
from backend.business.shared import ServiceConfigurationError, ServiceIntegrationError
from backend.infra.repositories import SettingsRepository
from backend.main import app
from backend.stock_api.mx.self_select import MxSelfSelectClient


@pytest.mark.asyncio
async def test_watchlist_queries_shared_client_with_saved_key_and_preserves_all_rows(
    api_client: httpx.AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with session_factory() as session:
        await SettingsRepository(session).save(
            AppSettings(mx_api_key="watchlist-test-key")
        )
        await session.commit()

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/api/claw/self-select/get")
        assert request.method == "POST"
        assert request.headers["apikey"] == "watchlist-test-key"
        assert json.loads(request.content) == {}
        return httpx.Response(
            200,
            json={
                "status": 0,
                "data": {
                    "allResults": {
                        "result": {
                            "columns": [
                                {"key": "SECURITY_CODE", "title": "股票代码"},
                                {"key": "SECURITY_NAME", "title": "股票名称"},
                            ],
                            "dataList": [
                                {
                                    "SECURITY_CODE": "600519",
                                    "SECURITY_NAME": "贵州茅台",
                                },
                                {
                                    "SECURITY_CODE": "000001",
                                    "SECURITY_NAME": "平安银行",
                                },
                            ],
                        }
                    }
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as upstream:
        monkeypatch.setattr(app.state.runtime, "mx_clients", None)
        monkeypatch.setattr(app.state.runtime, "mx_http_client", upstream)
        response = await api_client.get("/api/aniu/account/watchlist")

    assert response.status_code == 200
    assert response.json() == {
        "columns": [
            {"key": "SECURITY_CODE", "title": "股票代码"},
            {"key": "SECURITY_NAME", "title": "股票名称"},
        ],
        "items": [
            {"SECURITY_CODE": "600519", "SECURITY_NAME": "贵州茅台"},
            {"SECURITY_CODE": "000001", "SECURITY_NAME": "平安银行"},
        ],
    }
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_watchlist_requires_login_before_querying_upstream(
    api_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unexpected_query(self):
        raise AssertionError("unauthenticated requests must not query the watchlist")

    monkeypatch.setattr(MxSelfSelectClient, "query", unexpected_query)
    api_client.cookies.clear()
    response = await api_client.get("/api/aniu/account/watchlist")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_watchlist_exposes_no_manual_mutation_endpoint(
    api_client: httpx.AsyncClient, method: str
) -> None:
    response = await api_client.request(method, "/api/aniu/account/watchlist")
    assert response.status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ServiceConfigurationError("MX_APIKEY is not configured"), 503),
        (ServiceIntegrationError("自选股接口暂时不可用"), 502),
    ],
)
async def test_watchlist_reports_query_failures_instead_of_an_empty_list(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
) -> None:
    async def query(self):
        raise error

    monkeypatch.setattr(MxSelfSelectClient, "query", query)
    response = await api_client.get("/api/aniu/account/watchlist")
    assert response.status_code == status
    assert response.json()["error"]["message"] == str(error)
