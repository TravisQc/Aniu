"""Watchlist HTTP contracts, runtime wiring and invocation logs."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.business.shared import ServiceIntegrationError
from backend.business.stock_api_logs.models import StockApiToolCall
from backend.infra.integrations.agent_runner import _StageToolRegistry
from backend.infra.integrations.agent_runtime import AgentRuntimeFactory
from backend.stock_api import MxClients, MxHttpTransport, StockApiCall


@pytest.mark.asyncio
async def test_self_select_runtime_uses_shared_auth_and_records_query_add_delete() -> (
    None
):
    requests: list[httpx.Request] = []
    keys = ["query-key", "add-key", "delete-key"]
    query_response = {
        "status": 0,
        "data": {
            "allResults": {
                "result": {
                    "columns": [{"key": "SECURITY_CODE", "title": "股票代码"}],
                    "dataList": [{"SECURITY_CODE": "600519"}],
                }
            }
        },
    }

    async def resolve_key() -> str:
        return keys[len(requests)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == keys[len(requests)]
        assert request.headers["content-type"] == "application/json"
        assert request.method == "POST"
        requests.append(request)
        result = (
            query_response if len(requests) == 1 else {"code": 0, "message": "成功"}
        )
        return httpx.Response(200, json=result)

    persisted: list[StockApiToolCall] = []

    async def record(call: StockApiToolCall) -> None:
        persisted.append(call)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        clients = MxClients.create(api_key_resolver=resolve_key, http_client=http)
        clients.transport.base_url = "https://mkapi2.dfcfs.com/finskillshub"
        assert clients.self_select.transport is clients.transport
        source = await AgentRuntimeFactory(
            mx_research_client=clients.research,
            mx_portfolio_client=clients.portfolio,
            mx_trading_client=clients.trading,
            mx_self_select_client=clients.self_select,
        ).build_tool_registry()
        registry = _StageToolRegistry(
            source,
            "Run",
            run_id=1,
            invocation_session_factory=None,
            stock_api_tool_call_logger=record,
        )
        summary = _StageToolRegistry(
            source,
            "Summary",
            run_id=1,
            invocation_session_factory=None,
        )
        assert summary.list_tools() == []

        assert (
            await registry.call_idempotently(
                "query_self_select", tool_call_id="self-select-1", abort_signal=None
            )
            == query_response
        )
        queries = [
            "把600519添加到我的自选股列表",
            "把600519从我的自选股列表删除",
        ]
        for index, query in enumerate(queries, start=2):
            assert await registry.call_idempotently(
                "manage_self_select",
                tool_call_id=f"self-select-{index}",
                abort_signal=None,
                query=query,
            ) == {"code": 0, "message": "成功"}
        assert [str(request.url) for request in requests] == [
            "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/get",
            "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/manage",
            "https://mkapi2.dfcfs.com/finskillshub/api/claw/self-select/manage",
        ]
        assert [json.loads(request.content) for request in requests] == [
            {},
            {"query": queries[0]},
            {"query": queries[1]},
        ]
        assert len(persisted) == 3
        assert all(
            (call.tool_source, call.tool_id, call.status)
            == ("mx", "self_select", "success")
            for call in persisted
        )
        assert [call.parameters for call in persisted] == [
            {},
            {"query": queries[0]},
            {"query": queries[1]},
        ]
        details = registry.stock_api_call_details("self-select-1")
        assert details[0]["operation_id"] == "query_self_select"
        assert details[0]["interface_identifier"] == "自选股管理 · 查询列表"
        details = registry.stock_api_call_details("self-select-2")
        assert details[0]["operation_id"] == "manage_self_select"
        assert details[0]["interface_identifier"] == "自选股管理 · 添加或删除"
        await clients.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["get", "manage"])
@pytest.mark.parametrize(
    "response",
    [
        {"status": 401, "message": "API密钥不存在"},
        {"code": 0, "data": {"code": 113, "message": "今日调用次数已达上限"}},
    ],
)
async def test_self_select_rejects_root_and_nested_business_failures(
    endpoint: str, response: dict[str, object]
) -> None:
    transport = MxHttpTransport(
        api_key="test-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response)
        ),
        request_interval=0,
        rate_limit_retries=0,
    )
    try:
        with pytest.raises(ServiceIntegrationError):
            await transport.post_envelope(f"/api/claw/self-select/{endpoint}", {})
    finally:
        await transport.aclose()


@pytest.mark.asyncio
async def test_self_select_query_retries_transient_rate_limit_and_logs_attempts() -> (
    None
):
    requests = 0
    logs: list[StockApiCall] = []

    async def record(call: StockApiCall) -> None:
        logs.append(call)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(429, json={"message": "请求频率过高"})
        return httpx.Response(200, json={"status": 0, "data": {}})

    transport = MxHttpTransport(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        call_logger=record,
        request_interval=0,
        rate_limit_retries=1,
        rate_limit_backoff=0,
    )
    try:
        assert await transport.post_envelope("/api/claw/self-select/get", {}) == {
            "status": 0,
            "data": {},
        }
        assert requests == 2
        assert [call.status for call in logs] == ["failed", "success"]
        assert all(call.operation_id == "query_self_select" for call in logs)
    finally:
        await transport.aclose()
