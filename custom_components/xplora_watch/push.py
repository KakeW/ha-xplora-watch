"""Opt-in FCM receiver. Never acknowledges Xplora chats as read."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from firebase_messaging import FcmPushClient, FcmRegisterConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator import XploraDataUpdateCoordinator
from .push_config import FIREBASE_CONFIG
from .pyxplora_api.gql_mutations import FCM_M

CONF_PUSH = "push_notifications"
EVENT_MESSAGE = "xplora_watch_message"
# Message types present in the official iOS bundle; only text has a live fixture so far.
CHAT_TYPES = {"chat_text", "chat_voice", "chat_emoticon", "chat_image", "chat_video"}
_LOGGER = logging.getLogger(__name__)


def parse_message(payload: Any) -> dict[str, str] | None:
    """Allowlist message fields; do not expose raw push credentials or media URLs."""
    try:
        content = payload["data"]["content"]
        content = json.loads(content) if isinstance(content, str) else content
        kind = content.get("msg_type", "")
        if not isinstance(kind, str) or kind not in CHAT_TYPES:
            return None
        if not content.get("sender") or not content.get("msg_id"):
            return None
        return {key: str(content.get(source, "")) for key, source in {
            "sender_id": "sender", "sender_name": "sender_name", "message_id": "msg_id",
            "message_type": "msg_type", "text": "text", "timestamp": "time",
        }.items()}
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


class XploraPush:
    """Persist registration and deduplication; supervise the library's connection."""

    def __init__(self, hass: HomeAssistant, coordinator: XploraDataUpdateCoordinator, entry_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entry_id = entry_id
        self.store: Store = Store(hass, 1, f"{DOMAIN}.{entry_id}.push", private=True)
        self.state: dict[str, Any] = {}
        self.client: Any = None
        self.task: asyncio.Task | None = None
        self.queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=256)
        self.stopping = False

    def start(self) -> None:
        """Network startup must not block integration setup."""
        self.task = self.hass.async_create_background_task(self.run(), f"Xplora push {self.entry_id}")

    def received(self, payload: Any, _persistent_id: Any, _context: Any) -> None:
        message = parse_message(payload)
        if message and not self.stopping:
            try:
                self.queue.put_nowait(message)
            except asyncio.QueueFull:
                _LOGGER.warning("Xplora push queue full; message skipped")

    async def consume(self, message: dict[str, str]) -> None:
        """Serialize delivery and persist before publishing to suppress replay after restart."""
        key = message["sender_id"] + ":" + message["message_id"]
        seen = self.state.get("seen", [])
        if key in seen:
            return
        self.state["seen"] = (seen + [key])[-2048:]
        await self.store.async_save(self.state)
        self.hass.bus.async_fire(EVENT_MESSAGE, {"entry_id": self.entry_id, **message})

    async def run(self) -> None:
        try:
            self.state = await self.store.async_load() or {}
            self.state.setdefault("client_id", str(uuid4()))
            await self.store.async_save(self.state)
            while not self.stopping:
                try:
                    await self.connect()
                    while not self.stopping:
                        try:
                            message = await asyncio.wait_for(self.queue.get(), 60)
                            await self.consume(message)
                        except TimeoutError:
                            if self.client.run_state.name == "STOPPED" or any(task.done() for task in self.client.tasks):
                                raise ConnectionError("Push receiver stopped")
                        # Re-bind after the coordinator replaces an expired Xplora session.
                        token = self.coordinator.controller.dump_session().get("issue_token", {}).get("token")
                        if token != self.bound_session:
                            await self.bind()
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 -- keep optional push isolated from HA setup
                    _LOGGER.warning("Xplora push unavailable (%s); retrying in 5 minutes", type(err).__name__)
                finally:
                    await self.disconnect()
                await asyncio.sleep(300)
        finally:
            await self.disconnect()

    async def connect(self) -> None:
        self.client = FcmPushClient(
            self.received, FcmRegisterConfig(
                FIREBASE_CONFIG["project_id"], FIREBASE_CONFIG["app_id"],
                FIREBASE_CONFIG["api_key"], FIREBASE_CONFIG["messaging_sender_id"],
            ), self.state.get("credentials"),
            http_client_session=aiohttp_client.async_get_clientsession(self.hass),
        )
        self.fcm_token = await asyncio.wait_for(self.client.checkin_or_register(), 60)
        self.state["credentials"] = self.client.credentials
        await self.store.async_save(self.state)
        await self.bind()
        await self.client.start()
        _LOGGER.info("Xplora push receiver started")

    async def bind(self) -> None:
        controller = self.coordinator.controller
        result = await self.coordinator._with_recovery(
            lambda: controller._gql_handler.runAuthorizedGqlQuery_a(
                FCM_M["setTokenM"], {
                    "clientId": self.state["client_id"], "fcmToken": self.fcm_token,
                    "manufacturer": "Home Assistant", "brand": "Home Assistant", "model": "Push receiver",
                    "osVer": "1", "userLang": "en-GB", "timeZone": self.coordinator._history_tz(),
                }, "setFCMToken",
            )
        )
        if result.get("errors") or (result.get("data") or {}).get("setFCMToken") is not True:
            raise ConnectionError("Xplora rejected push registration")
        self.bound_session = controller.dump_session().get("issue_token", {}).get("token")

    async def disconnect(self) -> None:
        client, self.client = self.client, None
        if client is not None and client.stopping_lock is not None:
            tasks = list(client.tasks)
            await client.stop()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        self.stopping = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
