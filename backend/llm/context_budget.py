"""Shared input and output token budgets for model-backed workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 32_768
DEFAULT_KEEP_RECENT_TOKENS = 20_000
SAFETY_MARGIN_RATIO = 0.05


class _RuntimeTokenLimits(Protocol):
    @property
    def context_window_tokens(self) -> int: ...

    @property
    def max_output_tokens(self) -> int: ...


class ContextBudgetExceededError(RuntimeError):
    """Raised when complete messages do not fit the configured context budget."""


@dataclass(frozen=True, slots=True)
class ContextBudgetConfig:
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    @classmethod
    def from_runtime(cls, runtime: _RuntimeTokenLimits | None) -> ContextBudgetConfig:
        if runtime is None:
            return cls()
        window = max(1_000, int(runtime.context_window_tokens))
        return cls(
            context_window_tokens=window,
            max_output_tokens=max(1, int(runtime.max_output_tokens)),
        )

    @property
    def output_reserve_tokens(self) -> int:
        return min(self.max_output_tokens, max(1, self.context_window_tokens // 3))

    @property
    def safety_margin_tokens(self) -> int:
        return max(64, int(self.context_window_tokens * SAFETY_MARGIN_RATIO))

    @property
    def token_budget(self) -> int:
        return max(
            1,
            self.context_window_tokens
            - self.output_reserve_tokens
            - self.safety_margin_tokens,
        )

    @property
    def keep_recent_tokens(self) -> int:
        return max(1, min(DEFAULT_KEEP_RECENT_TOKENS, self.token_budget // 4))

    @property
    def summary_output_tokens(self) -> int:
        return max(
            1,
            min(8_192, self.output_reserve_tokens // 2, self.max_output_tokens),
        )

    def input_budget_for_output_tokens(self, output_tokens: int) -> int:
        """Return the largest safe input for a requested output ceiling."""

        reserved_output = min(max(1, output_tokens), self.max_output_tokens)
        return max(
            1,
            self.context_window_tokens - reserved_output - self.safety_margin_tokens,
        )

    def output_tokens_for_input(
        self,
        input_tokens: int,
        *,
        requested_max_output_tokens: int | None = None,
    ) -> int:
        """Clamp an outgoing output cap to the room left by actual input."""

        requested = (
            self.max_output_tokens
            if requested_max_output_tokens is None
            else min(max(1, requested_max_output_tokens), self.max_output_tokens)
        )
        available = (
            self.context_window_tokens
            - max(0, input_tokens)
            - self.safety_margin_tokens
        )
        if available < 1:
            raise ContextBudgetExceededError(
                "agent context leaves no room for a model response "
                f"(estimated_input={input_tokens}, "
                f"window={self.context_window_tokens})"
            )
        return min(requested, available)


__all__ = [
    "DEFAULT_CONTEXT_WINDOW_TOKENS",
    "DEFAULT_KEEP_RECENT_TOKENS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "SAFETY_MARGIN_RATIO",
    "ContextBudgetConfig",
    "ContextBudgetExceededError",
]
