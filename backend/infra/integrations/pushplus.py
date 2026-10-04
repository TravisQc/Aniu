"""PushPlus HTTP integration primitives."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from backend.business.settings import AppSettings, PushplusChannel
from backend.infra.repositories.settings_repo import SettingsRepository
from backend.stock_api.mx.trading_parser import ParsedTradeIntent

logger = logging.getLogger(__name__)

PUSHPLUS_SEND_URL = "https://www.pushplus.plus/send"


class PushplusError(RuntimeError):
    """Raised when PushPlus cannot accept a notification."""


@dataclass(frozen=True, slots=True)
class TradeNotification:
    """Normalized fields included in a trade notification."""

    stock_name: str
    stock_code: str
    direction: str
    quantity: int
    price: float
    total_amount: float


def normalize_trade_notification(
    result: object,
    intent: ParsedTradeIntent,
    *,
    fallback_stock_name: str | None = None,
) -> TradeNotification:
    """Extract stable trade fields from the MX response envelope."""

    payload = intent.payload
    candidates = _mapping_candidates(result)
    stock_code = _first_text(
        candidates, "stockCode", "stock_code", "secCode", "symbol"
    )
    if stock_code is None:
        stock_code = _first_six_digit(candidates, "code")
    stock_code = stock_code or str(payload["stockCode"])
    stock_name = _first_text(
        candidates,
        "stockName",
        "stock_name",
        "secName",
        "symbolName",
        "name",
    )
    stock_name = stock_name or fallback_stock_name or stock_code
    quantity = _first_positive_int(
        candidates,
        "filledQuantity",
        "filled_quantity",
        "dealQty",
        "tradeCount",
        "quantity",
        "orderQty",
        "entrustQty",
    )
    if quantity is None:
        quantity = _coerce_int(payload.get("quantity"))
    if quantity is None:
        raise PushplusError("trade intent does not include a usable quantity")
    price = _first_positive_float(
        candidates,
        "filledPrice",
        "filled_price",
        "dealPrice",
        "tradePrice",
        "price",
        "orderPrice",
        "entrustPrice",
    )
    if price is None:
        price = _coerce_float(payload.get("price"))
    if price is None:
        raise PushplusError("trade intent does not include a usable price")
    direction = "buy" if str(payload["type"]) == "buy" else "sell"
    return TradeNotification(
        stock_name=stock_name,
        stock_code=stock_code,
        direction=direction,
        quantity=quantity,
        price=price,
        total_amount=quantity * price,
    )


def format_trade_notification(trade: TradeNotification) -> str:
    """Format a predictable plain-text PushPlus transaction summary."""

    direction = "买入" if trade.direction == "buy" else "卖出"
    return "\n".join(
        (
            "模拟交易已成功",
            f"股票名称：{trade.stock_name}",
            f"股票代码：{trade.stock_code}",
            f"交易方向：{direction}",
            f"交易数量：{trade.quantity} 股",
            f"交易总额：{trade.total_amount:.2f} 元",
        )
    )


def _mapping_candidates(value: object) -> tuple[dict[str, object], ...]:
    candidates: list[dict[str, object]] = []
    current = value
    for _ in range(4):
        if not isinstance(current, dict):
            break
        candidates.append(current)
        nested = current.get("data")
        if isinstance(nested, dict):
            current = nested
            continue
        nested = current.get("result")
        if isinstance(nested, dict):
            current = nested
            continue
        break
    return tuple(candidates)


def _first_text(candidates: tuple[dict[str, object], ...], *keys: str) -> str | None:
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _first_six_digit(
    candidates: tuple[dict[str, object], ...], *keys: str
) -> str | None:
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            text = str(value).strip() if value is not None else ""
            if len(text) == 6 and text.isdigit():
                return text
    return None


def _coerce_int(value: object) -> int | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        return int(value)
    except (ValueError, OverflowError):
        return None


def _coerce_float(value: object) -> float | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _first_positive_int(
    candidates: tuple[dict[str, object], ...], *keys: str
) -> int | None:
    for candidate in candidates:
        for key in keys:
            parsed = _coerce_int(candidate.get(key))
            if parsed is not None and parsed > 0:
                return parsed
    return None


def _first_positive_float(
    candidates: tuple[dict[str, object], ...], *keys: str
) -> float | None:
    for candidate in candidates:
        for key in keys:
            parsed = _coerce_float(candidate.get(key))
            if parsed is not None and parsed > 0:
                return parsed
    return None


class PushplusClient:
    """Small bounded client for the PushPlus message endpoint."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = http_client
        self._timeout = timeout
        self._owns_client = False

    async def send(
        self,
        *,
        token: str,
        title: str,
        content: str,
        channel: PushplusChannel,
        option: str | None = None,
    ) -> dict[str, Any]:
        normalized_token = token.strip()
        if not normalized_token:
            raise PushplusError("PushPlus token is not configured")
        normalized_title = title.strip()
        normalized_content = content.strip()
        if not normalized_title or not normalized_content:
            raise PushplusError("PushPlus title and content must not be blank")

        body: dict[str, object] = {
            "token": normalized_token,
            "title": normalized_title,
            "content": normalized_content,
            "template": "txt",
            "channel": channel.value,
        }
        if channel is PushplusChannel.WEBHOOK:
            normalized_option = (option or "").strip()
            if not normalized_option:
                raise PushplusError("PushPlus webhook option is not configured")
            body["option"] = normalized_option
        elif option is not None:
            raise PushplusError("PushPlus option is only valid for webhook")

        try:
            response = await self._ensure_client().post(
                PUSHPLUS_SEND_URL,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PushplusError(f"PushPlus request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise PushplusError("PushPlus response must be an object")
        if str(payload.get("code") or "") != "200":
            message = str(payload.get("msg") or "PushPlus rejected the message")
            raise PushplusError(f"PushPlus rejected the message: {message}")
        return payload

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._owns_client = True
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
            self._owns_client = False


class PushplusTradeNotifier:
    """Resolve current settings and send one successful trade summary."""

    def __init__(
        self,
        *,
        session_factory: object,
        client: PushplusClient,
        portfolio: object | None = None,
        error_logger: Callable[..., object] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._portfolio = portfolio
        self._error_logger = error_logger or logger.warning

    async def notify(
        self,
        *,
        result: object,
        intent: ParsedTradeIntent,
    ) -> bool:
        settings = await self._load_settings()
        if settings is None or not settings.pushplus.enabled:
            return False
        token = settings.pushplus_token
        if not token:
            return False

        fallback_stock_name = await self._find_stock_name(
            str(intent.payload["stockCode"])
        )
        trade = normalize_trade_notification(
            result,
            intent,
            fallback_stock_name=fallback_stock_name,
        )
        try:
            await self._client.send(
                token=token,
                title="Aniu 模拟交易通知",
                content=format_trade_notification(trade),
                channel=settings.pushplus.channel,
                option=settings.pushplus.webhook_option,
            )
        except Exception as exc:  # noqa: BLE001 - notification must not fail trade
            safe_error = str(exc).replace(token, "[redacted]")
            if settings.pushplus.webhook_option:
                safe_error = safe_error.replace(
                    settings.pushplus.webhook_option, "[redacted]"
                )
            self._error_logger(
                "PushPlus trade notification failed channel=%s error=%s",
                settings.pushplus.channel.value,
                safe_error,
            )
            return False
        return True

    async def _load_settings(self) -> AppSettings | None:
        factory = self._session_factory
        if not callable(factory):
            return None
        async with factory() as session:
            return await SettingsRepository(session).get()

    async def _find_stock_name(self, stock_code: str) -> str | None:
        if self._portfolio is None:
            return None
        for method_name in ("get_orders", "get_positions"):
            method = getattr(self._portfolio, method_name, None)
            if not callable(method):
                continue
            try:
                items = await method()
            except Exception:
                continue
            if not isinstance(items, list):
                continue
            for item in reversed(items):
                if str(getattr(item, "symbol", "")) != stock_code:
                    continue
                stock_name = str(getattr(item, "stock_name", "")).strip()
                if stock_name:
                    return stock_name
        return None


__all__ = [
    "PUSHPLUS_SEND_URL",
    "PushplusClient",
    "PushplusError",
    "PushplusTradeNotifier",
    "TradeNotification",
    "format_trade_notification",
    "normalize_trade_notification",
]
