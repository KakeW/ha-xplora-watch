"""Per-watch automatic refresh coalescing and freshness gate."""

from __future__ import annotations

import asyncio
from typing import Any

from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.const import CHAT_READ_FLAG_UNREAD, SENSOR_MESSAGE
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_USER_ID, DEFAULT_WUID, make_device_list_payload


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


async def test_push_refresh_keeps_message_derived_unread_count_until_device_list_catches_up(
    coordinator: XploraDataUpdateCoordinator, graphql_operations
) -> None:
    """A chat push can arrive before Xplora's deviceList unread count catches up."""
    graphql_operations["Chats"] = {
        "data": {
            "chatsNew": {
                "offset": 0,
                "limit": 10,
                "list": [
                    {
                        "id": "chat-1",
                        "msgId": "message-1",
                        "readFlag": CHAT_READ_FLAG_UNREAD,
                        "sender": {"id": DEFAULT_WUID, "userId": DEFAULT_WUID, "name": "Child"},
                        "receiver": {"id": DEFAULT_USER_ID},
                        "data": {"text": "Hi", "sender_name": "Child", "delete_flag": 0},
                        "create": 1700000000,
                        "type": "TEXT",
                    }
                ],
            }
        }
    }
    graphql_operations["deviceList"] = {"data": make_device_list_payload(unread_chat_message_count=0)}

    await coordinator.controller.setDevices([DEFAULT_WUID])
    await coordinator.message_data(DEFAULT_WUID, 10, False)
    assert coordinator.data[DEFAULT_WUID]["unreadMsg"] == 1

    await coordinator.async_refresh_watch_cache(DEFAULT_WUID, include_chats=False, force=True)

    assert coordinator.data[DEFAULT_WUID]["unreadMsg"] == 1
    assert coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]["list"][0]["msgId"] == "message-1"
