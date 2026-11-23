"""MX account watchlist query and management client."""

from __future__ import annotations

from dataclasses import dataclass

from backend.stock_api.mx.http import MxHttpTransport


@dataclass(slots=True)
class MxSelfSelectClient:
    transport: MxHttpTransport

    async def query(self) -> dict[str, object]:
        return await self.transport.post_envelope("/api/claw/self-select/get", {})

    async def manage(self, query: str) -> dict[str, object]:
        text = query.strip()
        if not text:
            raise ValueError("自选股管理指令不能为空")
        return await self.transport.post_envelope(
            "/api/claw/self-select/manage",
            {"query": text},
        )


__all__ = ["MxSelfSelectClient"]
