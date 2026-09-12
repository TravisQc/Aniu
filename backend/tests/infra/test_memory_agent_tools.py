"""Tests for Run-stage memory tools."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agent.kernel.runtime_config import LlmRuntimeConfig
from backend.agent.tools import ToolRegistry
from backend.business.memories import MemoryService
from backend.business.runs import StrategyRun, StrategySnapshot
from backend.business.runs.execution import RunExecutionContext
from backend.business.shared.enums import TriggerSource
from backend.infra.integrations.agent_runner import (
    AgentRunnerFactoryAdapter,
    _StageToolRegistry,
)
from backend.infra.integrations.agent_runtime import AgentRuntimeFactory
from backend.infra.integrations.dream_agent import DreamToolRegistry
from backend.infra.integrations.dream_agent_tools import (
    DreamReportReadTool,
    MemoryListTool,
)
from backend.infra.integrations.memory_agent_tools import (
    MemoryReadTool,
    MemoryWriteTool,
)
from backend.infra.repositories.memory_repo import MemoryRepository
from backend.llm import ModelProtocol
from backend.llm.providers.extract import _claude_tools_spec, _openai_tool_spec


@pytest.mark.asyncio
async def test_memory_tools_write_then_read_across_sessions(session_factory) -> None:
    writer = MemoryWriteTool(session_factory)
    created = await writer.run_for_call(
        run_id=200,
        tool_call_id="memory-write-1",
        operation="create",
        content="弱市缩量反弹时不要追高。",
        reason="本次运行观察到追高后回撤。",
    )

    assert created["status"] == "ok"
    assert created["item"]["version"] == 1
    reader = MemoryReadTool(session_factory)
    loaded = await reader.run(keywords="弱市 追高", limit=5)

    assert loaded["status"] == "ok"
    assert loaded["items"][0]["content"] == "弱市缩量反弹时不要追高。"
    assert loaded["items"][0]["reason"] == "本次运行观察到追高后回撤。"


@pytest.mark.asyncio
async def test_dream_report_tool_accepts_harness_metadata(session_factory) -> None:
    result = await DreamReportReadTool(session_factory, date(2026, 8, 18)).run_for_call(
        run_id=20260818401,
        tool_call_id="dream-report-1",
        offset=0,
        limit=10,
    )

    assert result["status"] == "ok"
    assert result["reports"] == []


@pytest.mark.asyncio
async def test_memory_read_schema_exposes_match_mode(session_factory) -> None:
    definition = MemoryReadTool(session_factory).to_tool_definition()
    parameters = definition["parameters"]

    assert set(parameters["properties"]) == {"keywords", "match_mode", "limit"}
    assert parameters["properties"]["match_mode"]["enum"] == ["and", "or"]
    assert parameters["required"] == ["keywords", "match_mode"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operations",
    [
        ("create", "update", "delete"),
        (" CREATE ", "\tUPDATE\n", " Delete "),
    ],
    ids=["canonical", "normalized"],
)
async def test_dream_memory_write_supports_update_and_soft_delete(
    session_factory, operations
) -> None:
    task_id = 20260911401
    registry = DreamToolRegistry(
        task_id,
        [MemoryWriteTool(session_factory), MemoryListTool(session_factory)],
    )
    created = await registry.call_idempotently(
        "memory_write",
        tool_call_id="memory-write-1",
        abort_signal=None,
        operation=operations[0],
        content="弱市不要追高。",
        reason="本次运行观察到追高后回撤。",
    )
    listed = await registry.call("memory_list")
    item = listed["items"][0]
    assert item == created["item"]
    memory_id = item["id"]

    updated = await registry.call_idempotently(
        "memory_write",
        tool_call_id="memory-write-2",
        abort_signal=None,
        operation=operations[1],
        memory_id=memory_id,
        expected_version=item["version"],
        content="弱市缩量反弹时不要追高。",
        reason="补充成交量确认条件。",
    )
    assert updated["item"]["version"] == 2
    assert updated["item"]["updated_task_id"] == task_id
    listed = await registry.call("memory_list")
    assert listed["items"] == [updated["item"]]

    with pytest.raises(ValueError, match="memory version conflict"):
        await registry.call_idempotently(
            "memory_write",
            tool_call_id="memory-write-stale-delete",
            abort_signal=None,
            operation=operations[2],
            memory_id=memory_id,
            expected_version=item["version"],
        )

    deleted = await registry.call_idempotently(
        "memory_write",
        tool_call_id="memory-write-3",
        abort_signal=None,
        operation=operations[2],
        memory_id=memory_id,
        expected_version=updated["item"]["version"],
    )
    assert deleted["item"]["version"] == 3
    assert deleted["item"]["deleted_at"] is not None
    listed = await registry.call("memory_list")
    assert listed["items"] == []
    async with session_factory() as session:
        assert await MemoryRepository(session).count_activities(task_id=task_id) == 3


@pytest.mark.asyncio
async def test_memory_write_schema_exposes_operations_to_providers(
    session_factory,
) -> None:
    definition = MemoryWriteTool(session_factory).to_tool_definition()
    for parameters in (
        _openai_tool_spec(definition)["function"]["parameters"],
        _claude_tools_spec([definition])[0]["input_schema"],
    ):
        assert parameters["type"] == "object"
        assert "oneOf" not in parameters
        assert parameters["required"] == ["operation"]
        assert parameters["additionalProperties"] is False
        properties = parameters["properties"]
        assert set(properties) == {
            "operation",
            "memory_id",
            "expected_version",
            "content",
            "reason",
        }
        assert properties["operation"]["type"] == "string"
        assert properties["operation"]["enum"] == ["create", "update", "delete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["merge", "soft_delete", "", None, 1, {}])
async def test_memory_write_rejects_unknown_operations_with_actionable_diagnostics(
    session_factory, caplog, operation
) -> None:
    writer = MemoryWriteTool(session_factory)
    created = await writer.run_for_call(
        run_id=200,
        tool_call_id="memory-write-seed",
        operation="create",
        content="原始记忆。",
        reason="原始依据。",
    )
    with pytest.raises(ValueError, match="unsupported memory operation") as caught:
        await writer.run_for_call(
            run_id=201,
            tool_call_id="memory-write-invalid",
            operation=operation,
            memory_id=created["item"]["id"],
            expected_version=created["item"]["version"],
            content="private-invalid-memory-content",
            reason="private-invalid-memory-reason",
        )

    message = str(caught.value)
    assert repr(operation) in message
    for supported in ("create", "update", "delete"):
        assert repr(supported) in message
    record = next(
        record
        for record in caplog.records
        if record.name == "backend.infra.integrations.memory_agent_tools"
    )
    assert record.run_id == 201
    assert record.tool_call_id == "memory-write-invalid"
    assert repr(operation) in record.getMessage()
    assert "memory_id=1" in record.getMessage()
    assert "expected_version=1" in record.getMessage()
    assert "private-invalid-memory" not in caplog.text
    listed = await MemoryListTool(session_factory).run()
    assert listed["items"] == [created["item"]]
    async with session_factory() as session:
        assert await MemoryRepository(session).count_activities() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "missing_field"),
    [
        ("create", "content"),
        ("create", "reason"),
        ("update", "memory_id"),
        ("update", "expected_version"),
        ("update", "content"),
        ("update", "reason"),
        ("delete", "memory_id"),
        ("delete", "expected_version"),
    ],
)
async def test_memory_write_enforces_operation_fields_at_runtime(
    session_factory, operation, missing_field
) -> None:
    arguments = {"operation": operation}
    if operation != "create":
        arguments.update(memory_id=16, expected_version=6)
    if operation != "delete":
        arguments.update(content="完整记忆内容。", reason="变更依据。")
    del arguments[missing_field]

    with pytest.raises(ValueError, match=f"requires {missing_field}"):
        await MemoryWriteTool(session_factory).run_for_call(
            run_id=20260911401,
            tool_call_id="memory-write-missing-field",
            **arguments,
        )
    async with session_factory() as session:
        assert await MemoryRepository(session).count_items() == 0
        assert await MemoryRepository(session).count_activities() == 0


@pytest.mark.asyncio
async def test_memory_read_returns_payload_when_activity_audit_fails(
    session_factory, monkeypatch
) -> None:
    async def fail_record_read(*_: object, **__: object) -> object:
        raise RuntimeError("activity database is unavailable")

    monkeypatch.setattr(MemoryService, "record_read", fail_record_read)

    result = await MemoryReadTool(session_factory).run_for_call(
        run_id=301,
        tool_call_id="memory-read-audit-failure",
        keywords="不存在的记忆",
        match_mode="and",
        limit=5,
    )

    assert result == {"status": "ok", "items": []}


@pytest.mark.asyncio
async def test_runtime_factory_registers_memory_tools_when_database_available(
    session_factory,
) -> None:
    registry = await AgentRuntimeFactory(
        session_factory=session_factory
    ).build_tool_registry()

    assert {"memory_read", "memory_write"}.issubset(registry.list_tool_names())
    assert registry.get("memory_read").enabled_stages == ("Run",)
    assert registry.get("memory_write").requires_market_open is False


class MemoryWriteClient:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, **_: object) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "memory-write-1",
                        "name": "memory_write",
                        "arguments": {
                            "operation": "create",
                            "content": "弱市缩量反弹时不要追高。",
                            "reason": "本次运行观察到追高后回撤。",
                        },
                    }
                ],
            }
        return {"content": "# Report", "tool_calls": []}


def _context(registry: ToolRegistry) -> RunExecutionContext:
    snapshot = StrategySnapshot(prompt_version="v1", risk_rules_version="v1")
    return RunExecutionContext(
        run=StrategyRun(300, TriggerSource.MANUAL, None, snapshot),
        snapshot=snapshot,
        tool_registry=registry,
        market_session_is_open=lambda: False,
    )


@pytest.mark.asyncio
async def test_run_allows_memory_write_closed_market_and_hides_tools_from_summary(
    session_factory,
) -> None:
    registry = ToolRegistry()
    registry.register(MemoryReadTool(session_factory))
    registry.register(MemoryWriteTool(session_factory))
    context = _context(registry)
    runtime = LlmRuntimeConfig(
        protocol=ModelProtocol.OPENAI_CHAT_COMPLETIONS,
        base_url="https://example.invalid",
        api_key="test",
        model="test-model",
    )
    runner = AgentRunnerFactoryAdapter(
        MemoryWriteClient(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        invocation_session_factory=session_factory,
    ).create(context, label="Run", runtime=runtime)

    result = await runner.prompt("执行任务")

    assert result.content == "# Report"
    assert any(
        activity["tool_name"] == "memory_write" and activity["status"] == "ok"
        for activity in result.tool_activity
    )
    summary_registry = _StageToolRegistry(
        registry,
        "Summary",
        run_id=300,
        invocation_session_factory=session_factory,
    )
    assert summary_registry.list_tools() == []
