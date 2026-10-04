from __future__ import annotations

import json

import httpx
import pytest

from backend.business.settings import PushplusChannel
from backend.infra.integrations.pushplus import PushplusClient, PushplusError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "option"),
    [
        (PushplusChannel.WECHAT, None),
        (PushplusChannel.CMCC, None),
        (PushplusChannel.WEBHOOK, "robot-code"),
    ],
)
async def test_pushplus_client_builds_supported_channel_requests(
    channel: PushplusChannel,
    option: str | None,
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "msg": "请求成功"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = PushplusClient(http_client=http_client)
    try:
        await client.send(
            token="pushplus-token",
            title="交易通知",
            content="买入测试",
            channel=channel,
            option=option,
        )
    finally:
        await http_client.aclose()

    assert len(requests) == 1
    assert requests[0].url == "https://www.pushplus.plus/send"
    assert json.loads(requests[0].content) == {
        "token": "pushplus-token",
        "title": "交易通知",
        "content": "买入测试",
        "template": "txt",
        "channel": channel.value,
        **({"option": option} if option is not None else {}),
    }


@pytest.mark.asyncio
async def test_pushplus_client_rejects_missing_webhook_option() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"code": 200})
        )
    )
    client = PushplusClient(http_client=http_client)
    with pytest.raises(PushplusError, match="webhook option"):
        await client.send(
            token="token",
            title="title",
            content="content",
            channel=PushplusChannel.WEBHOOK,
        )
    await http_client.aclose()


@pytest.mark.asyncio
async def test_pushplus_client_rejects_non_success_response() -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"code": 400, "msg": "token 无效"}
            )
        )
    )
    client = PushplusClient(http_client=http_client)
    with pytest.raises(PushplusError, match="rejected"):
        await client.send(
            token="token",
            title="title",
            content="content",
            channel=PushplusChannel.WECHAT,
        )
    await http_client.aclose()
