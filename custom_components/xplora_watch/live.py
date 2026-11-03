"""Bounded, per-watch live-location sessions shared by every dashboard client."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .pyxplora_api.exception_classes import AuthError, RateLimitError

if TYPE_CHECKING:
    from .coordinator import XploraDataUpdateCoordinator

LIVE_POLL_SECONDS = 15


class LiveTracking:
    """Start tracking once, read locations without locate commands, and stop on exit."""

    def __init__(self, coordinator: XploraDataUpdateCoordinator) -> None:
        self.coordinator = coordinator
        self.tasks: dict[str, asyncio.Task] = {}
        self.states: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.finish_tasks: dict[str, asyncio.Task] = {}

    def attributes(self, wuid: str) -> dict[str, Any]:
        return {
            "live_tracking_allowed": self.coordinator.is_admin.get(wuid, False),
            "live_tracking_active": False,
            "live_tracking_until": None,
            "live_tracking_error": None,
            "live_tracking_stop_pending": False,
            "live_tracking_received": False,
            **self.states.get(wuid, {}),
        }

    async def _command(self, wuid: str, *, start: bool) -> None:
        controller = self.coordinator.controller
        method = controller.getStartTrackingWatch if start else controller.getEndTrackingWatch
        result = await asyncio.wait_for(self.coordinator._with_recovery(lambda: method(wuid)), 30)
        # The schema returns an Int, but does not document individual success codes.
        # Reject absent/error sentinels rather than presenting an unacknowledged session as live.
        if type(result) is not int or result < 0:
            raise HomeAssistantError("Xplora did not acknowledge the tracking request")

    async def start(self, wuid: str, minutes: int = 5) -> None:
        if wuid not in self.coordinator._configured_wuids:
            raise HomeAssistantError("Unknown watch")
        if not self.coordinator.is_admin.get(wuid, False):
            raise HomeAssistantError("Live tracking requires the watch's primary guardian")
        if not 1 <= minutes <= 30:
            raise HomeAssistantError("Live tracking duration must be 1–30 minutes")
        async with self.locks.setdefault(wuid, asyncio.Lock()):
            if wuid in self.tasks and not self.tasks[wuid].done():
                return
            if self.states.get(wuid, {}).get("live_tracking_stop_pending"):
                raise HomeAssistantError("Retry stopping the previous tracking session first")
            await self._command(wuid, start=True)
            self.finish_tasks.pop(wuid, None)
            self.states[wuid] = {
                "live_tracking_active": True,
                "live_tracking_started_at": datetime.now(timezone.utc).isoformat(),
                "live_tracking_received": False,
                "live_tracking_until": (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(),
                "live_tracking_error": None,
                "live_tracking_stop_pending": False,
            }
            self.coordinator.async_update_listeners()
            deadline = asyncio.get_running_loop().time() + minutes * 60
            self.tasks[wuid] = self.coordinator.hass.async_create_background_task(self._run(wuid, deadline), f"Xplora live tracking {wuid}")

    async def stop(self, wuid: str) -> None:
        async with self.locks.setdefault(wuid, asyncio.Lock()):
            task = self.tasks.get(wuid)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await self._finish(wuid)
            elif self.states.get(wuid, {}).get("live_tracking_error"):
                # Allow retrying a failed remote stop even after the local loop ended.
                await self._command(wuid, start=False)
                self.states[wuid]["live_tracking_error"] = None
                self.states[wuid]["live_tracking_stop_pending"] = False
                self.coordinator.async_update_listeners()

    async def shutdown(self) -> None:
        await asyncio.gather(*(self.stop(wuid) for wuid in list(self.tasks)))

    async def _finish(self, wuid: str) -> None:
        """Run remote cleanup once, including cancellation before the worker first runs."""
        if wuid not in self.finish_tasks:
            self.finish_tasks[wuid] = self.coordinator.hass.async_create_background_task(
                self._stop_remote(wuid), f"Xplora stop live tracking {wuid}"
            )
        await asyncio.shield(self.finish_tasks[wuid])

    async def _stop_remote(self, wuid: str) -> None:
        try:
            await self._command(wuid, start=False)
        except Exception as err:
            self.states[wuid]["live_tracking_error"] = "Xplora did not confirm stopping; the remote session may still be active"
            self.states[wuid]["live_tracking_stop_pending"] = True
            self.coordinator._log.warning("Live tracking stop failed (%s)", type(err).__name__)
        self.states[wuid]["live_tracking_active"] = False
        self.states[wuid]["live_tracking_until"] = None
        self.tasks.pop(wuid, None)
        self.coordinator.async_update_listeners()

    async def _run(self, wuid: str, deadline: float) -> None:
        failures = 0
        try:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    await asyncio.wait_for(self.coordinator.async_read_live_location(wuid), 30)
                    failures = 0
                except AuthError, RateLimitError:
                    raise
                except Exception as err:
                    failures += 1
                    self.coordinator._log.warning("Live location read failed (%s)", type(err).__name__)
                    if failures >= 3:
                        raise HomeAssistantError("Live location updates failed repeatedly") from err
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining > 0:
                    await asyncio.sleep(min(LIVE_POLL_SECONDS, remaining))
        except asyncio.CancelledError:
            pass
        except Exception:
            self.states[wuid]["live_tracking_error"] = "Live location updates failed; tracking stopped"
        finally:
            await self._finish(wuid)
