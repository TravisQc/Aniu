"""Context budgeting for independent agent turns."""

from __future__ import annotations

from backend.llm import ChatMessage
from backend.llm.context import estimate_messages_tokens as _estimate_messages_tokens
from backend.llm.context_budget import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    DEFAULT_KEEP_RECENT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    SAFETY_MARGIN_RATIO,
    ContextBudgetConfig,
    ContextBudgetExceededError,
)


def ensure_context_budget(
    messages: list[ChatMessage],
    *,
    config: ContextBudgetConfig | None = None,
) -> list[ChatMessage]:
    cfg = config or ContextBudgetConfig()
    estimated = _estimate_messages_tokens(messages)
    if estimated <= cfg.token_budget:
        return messages
    raise ContextBudgetExceededError(
        "agent context exceeds "
        f"{cfg.token_budget} input tokens (estimated={estimated}, "
        f"window={cfg.context_window_tokens}, "
        f"output_reserve={cfg.output_reserve_tokens}); "
        "messages were not truncated"
    )


__all__ = [
    "DEFAULT_CONTEXT_WINDOW_TOKENS",
    "DEFAULT_KEEP_RECENT_TOKENS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "SAFETY_MARGIN_RATIO",
    "ContextBudgetConfig",
    "ContextBudgetExceededError",
    "ensure_context_budget",
]
