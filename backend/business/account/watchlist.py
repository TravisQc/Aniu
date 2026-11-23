"""Read-only projection of the MX account watchlist."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from backend.business.shared import ServiceIntegrationError


class WatchlistQueryPort(Protocol):
    async def query(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class WatchlistColumnDTO:
    key: str
    title: str


@dataclass(frozen=True, slots=True)
class WatchlistDTO:
    columns: list[WatchlistColumnDTO]
    items: list[dict[str, str | None]]


_COLUMN_TITLES = {
    "SECURITY_CODE": "股票代码",
    "SECUCODE": "证券代码",
    "SECURITY_NAME": "股票名称",
    "SECURITY_NAME_ABBR": "股票名称",
}


@dataclass(slots=True)
class WatchlistService:
    client: WatchlistQueryPort

    async def get_watchlist(self) -> WatchlistDTO:
        result: object = await self.client.query()
        for envelope_key in ("data", "allResults", "result"):
            if isinstance(result, dict) and envelope_key in result:
                result = result[envelope_key]
        if result is None or result == {}:
            return WatchlistDTO(columns=[], items=[])
        if not isinstance(result, dict) or "dataList" not in result:
            raise ServiceIntegrationError("自选股列表返回格式异常")

        rows = result["dataList"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ServiceIntegrationError("自选股列表返回格式异常")

        columns: list[WatchlistColumnDTO] = []
        keys: set[str] = set()
        source_columns = result.get("columns", [])
        if not isinstance(source_columns, list):
            raise ServiceIntegrationError("自选股列表字段格式异常")
        for column in source_columns:
            if not isinstance(column, dict):
                continue
            key = column.get("key")
            if not isinstance(key, str) or not key or key in keys:
                continue
            title = column.get("title")
            columns.append(
                WatchlistColumnDTO(
                    key=key,
                    title=title
                    if isinstance(title, str) and title
                    else _COLUMN_TITLES.get(key, key),
                )
            )
            keys.add(key)
        # Some responses omit column metadata. Keep every returned stock and
        # field visible, including fields appearing only in later rows.
        for row in rows:
            for key in row:
                if isinstance(key, str) and key not in keys:
                    columns.append(
                        WatchlistColumnDTO(key, _COLUMN_TITLES.get(key, key))
                    )
                    keys.add(key)

        return WatchlistDTO(
            columns=columns,
            items=[
                {column.key: _display_value(row.get(column.key)) for column in columns}
                for row in rows
            ],
        )


def _display_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)
