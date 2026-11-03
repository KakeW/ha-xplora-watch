"""Live session lifecycle and position publication without full-watch refreshes."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.xplora_watch.const import SENSOR_MESSAGE
from custom_components.xplora_watch.pyxplora_api.exception_classes import RateLimitError
from tests.xplora_watch.conftest import setup_service_target
from tests.xplora_watch.fixtures.graphql_payloads import DEFAULT_WUID


@pytest.fixture
def live(coordinator):
    coordinator.is_admin[DEFAULT_WUID] = True
    coordinator.controller.getStartTrackingWatch = AsyncMock(return_value=0)
    coordinator.controller.getEndTrackingWatch = AsyncMock(return_value=0)
    coordinator.async_read_live_location = AsyncMock()
    return coordinator.live


async def test_start_is_shared_and_explicit_stop_cleans_up(live):
    await live.start(DEFAULT_WUID, 5)
    await live.start(DEFAULT_WUID, 15)
    assert live.attributes(DEFAULT_WUID)["live_tracking_active"] is True
    live.coordinator.controller.getStartTrackingWatch.assert_awaited_once_with(DEFAULT_WUID)
    await live.stop(DEFAULT_WUID)
    live.coordinator.controller.getEndTrackingWatch.assert_awaited_once_with(DEFAULT_WUID)
    assert live.attributes(DEFAULT_WUID)["live_tracking_active"] is False
    assert not live.tasks


async def test_expiry_stops_remote_tracking(live):
    live.states[DEFAULT_WUID] = {"live_tracking_active": True}
    await live._run(DEFAULT_WUID, asyncio.get_running_loop().time() - 1)
    live.coordinator.controller.getEndTrackingWatch.assert_awaited_once_with(DEFAULT_WUID)
    assert live.attributes(DEFAULT_WUID)["live_tracking_active"] is False


async def test_shutdown_stops_active_tracking(live):
    await live.start(DEFAULT_WUID)
    await live.shutdown()
    assert not live.tasks
    live.coordinator.controller.getEndTrackingWatch.assert_awaited_once()


async def test_live_loop_reads_again_after_15_seconds_and_stops_on_rate_limit(live):
    live.coordinator.async_read_live_location.side_effect = [None, RateLimitError()]
    with patch("custom_components.xplora_watch.live.asyncio.sleep", new_callable=AsyncMock) as sleep:
        await live.start(DEFAULT_WUID)
        await live.tasks[DEFAULT_WUID]
    sleep.assert_awaited_once_with(15)
    assert live.coordinator.async_read_live_location.await_count == 2
    live.coordinator.controller.getEndTrackingWatch.assert_awaited_once()
    assert not live.attributes(DEFAULT_WUID)["live_tracking_active"]


@pytest.mark.parametrize("result", [None, -1, False])
async def test_missing_ack_does_not_start_loop(live, result):
    live.coordinator.controller.getStartTrackingWatch.return_value = result
    with pytest.raises(HomeAssistantError):
        await live.start(DEFAULT_WUID)
    assert not live.tasks
    assert not live.attributes(DEFAULT_WUID)["live_tracking_active"]


async def test_contact_cannot_start(live):
    live.coordinator.is_admin[DEFAULT_WUID] = False
    with pytest.raises(HomeAssistantError):
        await live.start(DEFAULT_WUID)
    live.coordinator.controller.getStartTrackingWatch.assert_not_awaited()


async def test_failed_stop_is_visible_and_can_be_retried(live):
    await live.start(DEFAULT_WUID)
    live.coordinator.controller.getEndTrackingWatch.return_value = -1
    await live.stop(DEFAULT_WUID)
    assert live.attributes(DEFAULT_WUID)["live_tracking_stop_pending"]
    live.coordinator.controller.getEndTrackingWatch.return_value = 0
    await live.stop(DEFAULT_WUID)
    assert not live.attributes(DEFAULT_WUID)["live_tracking_stop_pending"]


async def test_live_fix_updates_position_and_preserves_messages(coordinator_with_data):
    coord = coordinator_with_data
    before = coord.data[DEFAULT_WUID][SENSOR_MESSAGE]
    coord.live.states[DEFAULT_WUID] = {"live_tracking_started_at": "2026-01-01T00:00:00+00:00"}
    coord._consumers_any_enabled = lambda _: True
    coord.controller.loadWatchLocation = AsyncMock(
        return_value={
            "watch_last_location": {
                "lat": "60.2",
                "lng": "24.7",
                "tm": 1800000000,
                "rad": 12,
                "locateType": "GPS",
            }
        }
    )
    with patch.object(coord.controller, "askWatchLocate", new_callable=AsyncMock) as ask:
        await coord.async_read_live_location(DEFAULT_WUID)
    coord.controller.loadWatchLocation.assert_awaited_once_with(DEFAULT_WUID, with_ask=False)
    ask.assert_not_awaited()
    assert coord.data[DEFAULT_WUID]["lat"] == 60.2
    assert coord.data[DEFAULT_WUID]["lng"] == 24.7
    assert coord.data[DEFAULT_WUID][SENSOR_MESSAGE] == before
    assert coord.live.attributes(DEFAULT_WUID)["live_tracking_received"]
    assert any(point["tm"] == 1800000000000 for points in coord._loc_history[DEFAULT_WUID].values() for point in points)


async def test_old_live_fix_cannot_replace_newer_manual_fix(coordinator_with_data):
    coord = coordinator_with_data
    coord.data[DEFAULT_WUID]["lastTrackTime"] = "2030-01-01T00:00:00+00:00"
    before = coord.data[DEFAULT_WUID]["lat"]
    coord.controller.loadWatchLocation = AsyncMock(
        return_value={
            "watch_last_location": {
                "lat": "60.2",
                "lng": "24.7",
                "tm": 1700000000,
            }
        }
    )
    await coord.async_read_live_location(DEFAULT_WUID)
    assert coord.data[DEFAULT_WUID]["lat"] == before


async def test_services_dispatch_duration_and_stop_to_selected_watch(hass, coordinator_with_data):
    coord = coordinator_with_data
    devices = await setup_service_target(hass, coord)
    coord.live.start = AsyncMock()
    coord.live.stop = AsyncMock()
    await hass.services.async_call(
        "xplora_watch",
        "start_live_tracking",
        {
            "device_id": devices[DEFAULT_WUID],
            "duration_minutes": 15,
        },
        blocking=True,
    )
    coord.live.start.assert_awaited_once_with(DEFAULT_WUID, 15)
    await hass.services.async_call(
        "xplora_watch",
        "stop_live_tracking",
        {
            "device_id": devices[DEFAULT_WUID],
        },
        blocking=True,
    )
    coord.live.stop.assert_awaited_once_with(DEFAULT_WUID)
