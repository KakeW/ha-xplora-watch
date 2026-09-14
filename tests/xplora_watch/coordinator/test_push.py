"""Push payload validation, replay protection and failure isolation."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xplora_watch.push import EVENT_MESSAGE, XploraPush, parse_message


def payload(**changes):
    content = dict(msg_type="chat_text", sender="watch-test", sender_name="Child", msg_id=123, text="Hello", time=123)
    content.update(changes)
    return {"data": {"content": json.dumps(content)}}


def test_live_shape():
    message = parse_message(payload())
    assert message["text"] == "Hello"
    assert message["message_id"] == "123"
    assert "receiver" not in message


@pytest.mark.parametrize("value", [None, {}, {"data": {"content": "broken"}}, payload(msg_type="location"), payload(msg_type="chat_read"), payload(msg_id=None)])
def test_bad_or_nonchat_payload(value):
    assert parse_message(value) is None


async def test_replay_suppression_survives_reload(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    events = []
    hass.bus.async_listen(EVENT_MESSAGE, lambda event: events.append(event.data))
    message = parse_message(payload())
    await receiver.consume(message)
    restored = XploraPush(hass, coordinator, "test")
    restored.state = await restored.store.async_load()
    await restored.consume(message)
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0]["entry_id"] == "test"


async def test_distinct_sender_same_id(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    await receiver.consume(parse_message(payload()))
    await receiver.consume(parse_message(payload(sender="other")))
    assert len(receiver.state["seen"]) == 2


async def test_registration_failure(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    receiver.state = {"client_id": "test"}
    receiver.fcm_token = "dummy"
    coordinator._with_recovery = AsyncMock(return_value={"data": {"setFCMToken": False}})
    with pytest.raises(ConnectionError):
        await receiver.bind()


async def test_shutdown_cancels_worker(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    receiver.connect = AsyncMock(side_effect=ConnectionError())
    receiver.start()
    await receiver.stop()
    assert receiver.task.done()


async def test_connect_reuses_credentials_and_checks_ack(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    saved = {"test": "credentials"}
    receiver.state = {"client_id": "stable-id", "credentials": saved}
    coordinator._with_recovery = AsyncMock(return_value={"data": {"setFCMToken": True}})
    client = MagicMock()
    client.credentials = saved
    client.checkin_or_register = AsyncMock(return_value="fcm-token")
    client.start = AsyncMock()
    with patch("custom_components.xplora_watch.push.FcmPushClient", return_value=client) as factory:
        await receiver.connect()
    assert factory.call_args.args[2] == saved
    client.start.assert_awaited_once()
    assert (await receiver.store.async_load())["client_id"] == "stable-id"


async def test_unload_waits_for_client_stop(hass, coordinator):
    receiver = XploraPush(hass, coordinator, "test")
    client = MagicMock(tasks=[], stop=AsyncMock())
    receiver.client = client
    await receiver.disconnect()
    client.stop.assert_awaited_once()
    assert receiver.client is None
