"""Summary handoffs must fit the same budget as the agent's model request."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from backend.agent.kernel.context_budget import ContextBudgetConfig
from backend.agent.kernel.runtime_config import LlmRuntimeConfig
from backend.business.runs import StrategyRun, StrategySnapshot
from backend.business.runs.execution import RunExecutionContext, RunReport
from backend.business.runs.stages.summary_stage import SummaryStage
from backend.business.shared.enums import TriggerSource
from backend.infra.integrations.agent_runner import AgentRunnerFactoryAdapter
from backend.infra.integrations.agent_runtime import AgentRuntimeFactory
from backend.llm import ModelProtocol, estimate_provider_request_tokens


class RecordingSummaryClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def chat(self, **kwargs: object) -> dict[str, object]:
        request = dict(kwargs)
        # The harness appends its response to the message list after this call.
        request["messages"] = deepcopy(kwargs["messages"])
        request["tools"] = deepcopy(kwargs["tools"])
        self.calls.append(request)
        return {"content": "<section>Summary</section>", "tool_calls": []}


async def _generate_summary(runtime: LlmRuntimeConfig, report: RunReport):
    snapshot = StrategySnapshot(prompt_version="v3", risk_rules_version="risk-v1")
    context = RunExecutionContext(
        run=StrategyRun(1, TriggerSource.MANUAL, None, snapshot),
        snapshot=snapshot,
        llm_runtime=runtime,
        run_report=report,
    )
    client = RecordingSummaryClient()
    factory = AgentRunnerFactoryAdapter(
        client,  # type: ignore[arg-type]
        AgentRuntimeFactory(),
    )
    runner = factory.create(context, label="Summary", runtime=runtime)

    result = await SummaryStage().execute(context, runner)

    assert result.summary == "<section>Summary</section>"
    assert len(client.calls) == 1
    request = client.calls[0]
    config = ContextBudgetConfig.from_runtime(runtime)
    input_tokens = estimate_provider_request_tokens(
        request["messages"],
        request["tools"],
        protocol=runtime.protocol,
        model=runtime.model,
        provider_config=runtime.provider_config,
    )
    assert input_tokens <= config.token_budget
    assert 0 < request["max_output_tokens"] <= runtime.max_output_tokens
    assert (
        input_tokens + request["max_output_tokens"] + config.safety_margin_tokens
        <= runtime.context_window_tokens
    )
    user_message = next(
        message for message in request["messages"] if message["role"] == "user"
    )
    return json.loads(user_message["content"].split("summary_source_data:\n", 1)[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", list(ModelProtocol))
@pytest.mark.parametrize(
    ("window", "output"),
    [
        (16_000, 16_000),
        (128_000, 128_000),
        (128_000, 126_000),
        (1_000_000, 1_000_000),
        (128_000, 32_768),
    ],
)
async def test_summary_reaches_model_with_large_output_limits(
    protocol, window, output
) -> None:
    runtime = LlmRuntimeConfig(
        protocol=protocol,
        base_url="https://example.invalid",
        api_key="test",
        model="test-model",
        context_window_tokens=window,
        max_output_tokens=output,
    )
    report = RunReport(content="# Report\n\nNo trade.")

    payload = await _generate_summary(runtime, report)

    assert payload["run_report_markdown"] == report.content


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", list(ModelProtocol))
async def test_summary_trims_optional_evidence_to_shared_agent_budget(protocol) -> None:
    runtime = LlmRuntimeConfig(
        protocol=protocol,
        base_url="https://example.invalid",
        api_key="test",
        model="test-model",
        context_window_tokens=32_000,
        max_output_tokens=32_000,
    )
    query_content = "行情数据" * 20_000
    trade = {
        "tool_call_id": "trade-1",
        "tool_name": "trade",
        "status": "ok",
        "content": {"success": True, "orderId": "order-1"},
    }
    failed_query = {
        "tool_call_id": "query-error",
        "tool_name": "query_quote",
        "status": "error",
        "error": "upstream unavailable",
        "content": {"diagnostic": "complete error evidence"},
    }
    report = RunReport(
        content="# Report\n\nTrade execution and error evidence must be preserved.",
        tool_activity=(
            {
                "tool_call_id": "query-1",
                "tool_name": "query_quote",
                "status": "ok",
                "content": query_content,
            },
            trade,
            failed_query,
        ),
    )

    payload = await _generate_summary(runtime, report)

    assert payload["run_report_markdown"] == report.content
    assert payload["tool_calls"][0]["content"]["truncated"] is True
    assert payload["tool_calls"][1:] == [trade, failed_query]
    assert report.tool_activity[0]["content"] == query_content
