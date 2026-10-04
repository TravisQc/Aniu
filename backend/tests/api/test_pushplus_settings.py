from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_pushplus_settings_are_disabled_and_masked_by_default(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/aniu/settings")

    assert response.status_code == 200
    assert response.json()["pushplus"] == {
        "enabled": False,
        "channel": "wechat",
        "token_configured": False,
        "token_last_four": None,
        "webhook_option_configured": False,
        "webhook_option_last_four": None,
    }


@pytest.mark.asyncio
async def test_pushplus_settings_update_and_secret_redaction(
    api_client: AsyncClient,
) -> None:
    current = (await api_client.get("/api/aniu/settings")).json()

    response = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {
                "enabled": True,
                "channel": "wechat",
                "token": "pushplus-secret-token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["pushplus"] == {
        "enabled": True,
        "channel": "wechat",
        "token_configured": True,
        "token_last_four": "oken",
        "webhook_option_configured": False,
        "webhook_option_last_four": None,
    }
    assert "pushplus-secret-token" not in response.text

    reloaded = await api_client.get("/api/aniu/settings")
    assert reloaded.status_code == 200
    assert "pushplus-secret-token" not in reloaded.text
    assert reloaded.json()["pushplus"]["enabled"] is True


@pytest.mark.asyncio
async def test_pushplus_webhook_requires_option_and_accepts_valid_option(
    api_client: AsyncClient,
) -> None:
    current = (await api_client.get("/api/aniu/settings")).json()
    missing_option = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {"enabled": True, "channel": "webhook"},
        },
    )

    assert missing_option.status_code == 422
    assert "webhook_option" in missing_option.text

    current = (await api_client.get("/api/aniu/settings")).json()
    valid = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {
                "enabled": True,
                "channel": "webhook",
                "token": "pushplus-token",
                "webhook_option": "robot-code",
            },
        },
    )

    assert valid.status_code == 200
    assert valid.json()["pushplus"]["channel"] == "webhook"
    assert valid.json()["pushplus"]["webhook_option_configured"] is True
    assert valid.json()["pushplus"]["webhook_option_last_four"] == "code"


@pytest.mark.asyncio
async def test_pushplus_rejects_unsupported_channel_and_can_disable(
    api_client: AsyncClient,
) -> None:
    current = (await api_client.get("/api/aniu/settings")).json()
    invalid = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {"channel": "mail"},
        },
    )
    assert invalid.status_code == 422

    current = (await api_client.get("/api/aniu/settings")).json()
    enabled = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {
                "enabled": True,
                "channel": "wechat",
                "token": "pushplus-token",
            },
        },
    )
    assert enabled.status_code == 200

    current = enabled.json()
    disabled = await api_client.put(
        "/api/aniu/settings",
        json={
            "expected_revision": current["revision"],
            "pushplus": {"enabled": False},
        },
    )
    assert disabled.status_code == 200
    assert disabled.json()["pushplus"]["enabled"] is False
    assert disabled.json()["pushplus"]["token_configured"] is True
