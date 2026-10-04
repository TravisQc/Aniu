from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text

from backend.business.settings import AppSettings, PushplusChannel, PushplusSettings
from backend.infra.db.models import AppSettingsModel, SecretStoreModel
from backend.infra.db.session import create_engine, init_db
from backend.infra.repositories import SettingsRepository


@pytest.mark.asyncio
async def test_settings_repository_round_trips_pushplus_without_plaintext_secret(
    session_factory,
) -> None:
    async with session_factory() as session:
        repository = SettingsRepository(session)
        saved = await repository.save(
            AppSettings(
                pushplus=PushplusSettings(
                    enabled=True,
                    channel=PushplusChannel.WEBHOOK,
                    webhook_option="robot-code",
                ),
                pushplus_token="pushplus-secret",
            )
        )
        await session.commit()
        assert saved.pushplus_token == "pushplus-secret"

    async with session_factory() as session:
        loaded = await SettingsRepository(session).get()
        model = await session.scalar(select(AppSettingsModel))
        secrets = list(
            (
                await session.scalars(
                    select(SecretStoreModel).where(
                        SecretStoreModel.namespace == "app_settings"
                    )
                )
            ).all()
        )

    assert loaded is not None
    assert loaded.pushplus.enabled is True
    assert loaded.pushplus.channel is PushplusChannel.WEBHOOK
    assert loaded.pushplus.webhook_option == "robot-code"
    assert loaded.pushplus_token == "pushplus-secret"
    assert model is not None
    assert model.pushplus_settings_json == {
        "enabled": True,
        "channel": "webhook",
        "webhook_option": "robot-code",
    }
    assert {item.secret_name for item in secrets} == {"pushplus_token"}
    assert all(item.encrypted_value != "pushplus-secret" for item in secrets)


@pytest.mark.asyncio
async def test_init_db_adds_pushplus_settings_to_legacy_schema() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE app_settings DROP COLUMN pushplus_settings_json")
        )

    await init_db(engine)
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("app_settings")
            }
        )

    assert "pushplus_settings_json" in columns
    await engine.dispose()
