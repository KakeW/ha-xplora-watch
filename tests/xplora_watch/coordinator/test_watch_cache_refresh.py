"""Per-watch automatic refresh coalescing and freshness gate."""

from __future__ import annotations

import asyncio
from typing import Any

from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


async def test_overlapping_cache_refreshes_share_one_fetch(
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    coord = coordinator_with_data
    calls: list[tuple[Any, ...]] = []
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(targets=None, *, force_functions=False, include_chats=False):
        calls.append((targets, force_functions, include_chats))
        started.set()
        await release.wait()
        return {DEFAULT_WUID: {"fresh": True}}

    coord.async_update_xplora_data = fetch  # type: ignore[method-assign]
    first = asyncio.create_task(coord.async_refresh_watch_cache(DEFAULT_WUID))
    await started.wait()
    second = asyncio.create_task(coord.async_refresh_watch_cache(DEFAULT_WUID))
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [
        {DEFAULT_WUID: {"fresh": True}},
        {DEFAULT_WUID: {"fresh": True}},
    ]
    assert calls == [([DEFAULT_WUID], False, True)]


async def test_recent_cache_is_reused_but_push_can_force_refresh(
    coordinator_with_data: XploraDataUpdateCoordinator,
) -> None:
    coord = coordinator_with_data
    calls = 0

    async def fetch(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {DEFAULT_WUID: {"fresh": True}}

    coord.async_update_xplora_data = fetch  # type: ignore[method-assign]
    await coord.async_refresh_watch_cache(DEFAULT_WUID)
    await coord.async_refresh_watch_cache(DEFAULT_WUID)
    await coord.async_refresh_watch_cache(DEFAULT_WUID, force=True)

    assert calls == 2
