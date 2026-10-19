"""Call and power history uses Xplora's notification feed and is cached with chats."""

from __future__ import annotations

from typing import Any

from custom_components.xplora_watch.const import SENSOR_MESSAGE
from custom_components.xplora_watch.coordinator import XploraDataUpdateCoordinator
from custom_components.xplora_watch.pyxplora_api.exception_classes import AuthError
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
    call_event = {
        "id": "event-1",
        "msgId": "call-1",
        "readFlag": 1,
        "create": 1792340293,
        "type": "CALL_LOG",
        "data": {"call_name": call["callName"], "call_time": call["duration"], "call_number": call["callNumber"]},
        "sender": {"id": DEFAULT_WUID},
    }
    power_event = {"id": "event-2", "msgId": "power-1", "create": 1792340393, "type": "POWER_OFF", "data": {}}
    chat_message = {"id": "event-3", "msgId": "text-1", "create": 1792340493, "type": "TEXT", "data": {"text": "hello"}}
    graphql_operations["notifications"] = {
        "data": {"notifications": {"msgId": None, "offset": 0, "limit": 50, "total": 0, "list": [call_event, power_event, chat_message]}}
    }
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    await coordinator.message_data(DEFAULT_WUID, message_limit=10, remove_message=False)

    cached = coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]
    assert cached["call_log_list"] == [call_event, power_event]
    assert cached["list"] == []


async def test_call_log_failure_preserves_previous_cached_records(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """An API error should be visible, but must not erase the last successful cache."""
    old_call = {"time": "2026-10-18T16:18:13Z", "callName": "Previously cached"}
    coordinator.data = {DEFAULT_WUID: {SENSOR_MESSAGE: {"list": [], "call_log_list": [old_call]}}}
    graphql_operations["notifications"] = {"errors": [{"message": "Notifications unavailable"}]}
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    await coordinator.message_data(DEFAULT_WUID, message_limit=10, remove_message=False)

    cached = coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]
    assert cached["call_log_list"] == [old_call]
    assert cached["call_log_error"] == "Notifications unavailable"


async def test_expired_token_from_call_log_does_not_escape_as_account_reauth(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """An endpoint-specific auth error must not abort the whole integration refresh."""
    old_call = {"time": "2026-10-18T16:18:13Z", "callName": "Previously cached"}
    coordinator.data = {DEFAULT_WUID: {SENSOR_MESSAGE: {"list": [], "call_log_list": [old_call]}}}
    graphql_operations["notifications"] = {"errors": [{"code": "E000004", "message": "expired"}]}
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    await coordinator.message_data(DEFAULT_WUID, message_limit=10, remove_message=False)

    cached = coordinator.data[DEFAULT_WUID][SENSOR_MESSAGE]
    assert cached["call_log_list"] == [old_call]
    assert "token expired" in cached["call_log_error"]


async def test_nullable_call_logs_is_a_successful_empty_result(
    coordinator: XploraDataUpdateCoordinator,
    graphql_operations: dict[str, dict[str, Any]],
) -> None:
    """The shipped GraphQL schema allows a valid null callLogs value."""
    graphql_operations["notifications"] = {"data": {"notifications": {"list": None}}}
    await coordinator.controller.setDevices([DEFAULT_WUID], functions=frozenset())

    result = await coordinator.controller.getWatchCallLog(DEFAULT_WUID)

    assert result == {"list": []}
