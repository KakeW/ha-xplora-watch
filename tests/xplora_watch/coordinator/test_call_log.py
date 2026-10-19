"""The call log uses Xplora's dedicated device-level API and is cached with chats."""

from __future__ import annotations

from typing import Any

from custom_components.xplora_watch.const import SENSOR_MESSAGE
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


async def test_message_data_fetches_and_caches_dedicated_call_log(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """Call history must not depend on whether a CALL_LOG item appears in chatsNew."""
    call = {
        "deviceId": f"device-{DEFAULT_WUID}",
        "time": "2026-10-18T16:18:13Z",
        "callNumber": "+358401234567",
        "callName": "Test contact",
        "callIcon": "",
        "callType": "VOICE",
        "callMode": "OUTGOING",
        "callModeCode": 1,
        "duration": "00:02:14",
    }
    graphql_operations["GetDeviceCallLog"] = {
        "data": {"getDeviceCallLog": {"watch": {"id": f"device-{DEFAULT_WUID}"}, "callLogs": [call]}}
    }
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    await coordinator.message_data(DEFAULT_WUID, message_limit=10, remove_message=False)

    cached = coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]
    assert cached["call_log_list"] == [call]
    assert cached["list"] == []


async def test_call_log_failure_preserves_previous_cached_records(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """An API error should be visible, but must not erase the last successful cache."""
    old_call = {"time": "2026-10-18T16:18:13Z", "callName": "Previously cached"}
    coordinator.data = {DEFAULT_WUID: {SENSOR_MESSAGE: {"list": [], "call_log_list": [old_call]}}}
    graphql_operations["GetDeviceCallLog"] = {"errors": [{"message": "Call log unavailable"}]}
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    await coordinator.message_data(DEFAULT_WUID, message_limit=10, remove_message=False)

    cached = coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]
    assert cached["call_log_list"] == [old_call]
    assert cached["call_log_error"] == "Call log unavailable"


async def test_nullable_call_logs_is_a_successful_empty_result(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """The shipped GraphQL schema allows a valid null callLogs value."""
    graphql_operations["GetDeviceCallLog"] = {"data": {"getDeviceCallLog": {"callLogs": None}}}
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    result = await coordinator.controller.getWatchCallLog(DEFAULT_WUID)

    assert result == {"list": []}
