"""Outgoing voice validation and Xplora's application-level acknowledgement."""

import base64
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.xplora_watch.voice import async_send_voice, voice_duration


def recording(frames=50):
    return base64.b64encode(b"#!AMR\n" + (b"\x04" + bytes(12)) * frames).decode()


@pytest.mark.parametrize("frames,seconds", [(50, 1), (51, 2), (750, 15)])
def test_duration_is_derived_from_frames(frames, seconds):
    assert voice_duration(recording(frames)) == seconds


@pytest.mark.parametrize("body", ["", "not base64!", recording(49), recording(751), recording()[:-4], "a" * 16000])
def test_invalid_or_unbounded_audio_is_rejected(body):
    with pytest.raises(ValueError):
        voice_duration(body)


async def test_send_uses_voice_type_and_requires_message_id(coordinator):
    handler = coordinator.controller._gql_handler
    with (
        patch.object(type(coordinator), "_configured_wuids", new_callable=PropertyMock, return_value=["watch-test"]),
        patch.object(
            handler, "runAuthorizedGqlQuery_a", new_callable=AsyncMock, return_value={"data": {"sendChatMsg": "accepted"}}
        ) as send,
    ):
        assert await async_send_voice(coordinator, "watch-test", recording()) == "accepted"
        assert "type: VOICE" in send.await_args.args[0]
        assert send.await_args.args[1] == {"uid": "watch-test", "body": recording(), "duration": 1}
        send.return_value = {"data": {"sendChatMsg": None}, "errors": [{"message": "Rejected"}]}
        with pytest.raises(HomeAssistantError):
            await async_send_voice(coordinator, "watch-test", recording())
        send.reset_mock()
        with pytest.raises(ValueError, match="Unknown watch"):
            await async_send_voice(coordinator, "someone-elses-watch", recording())
        send.assert_not_awaited()
