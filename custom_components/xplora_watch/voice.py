"""Bounded AMR-NB uploads from the chat composer."""

from __future__ import annotations

import base64
import binascii
import math

from homeassistant.exceptions import HomeAssistantError

from .coordinator import XploraDataUpdateCoordinator

# The shipped iOS schema documents base64 `body` on sendChatMsg (VOICE).
# Unlike the older sendChatVoice mutation this API does not require hashBody.
SEND_VOICE = """mutation SendChatMsg($uid: String!, $body: String!, $duration: Int!) {
  sendChatMsg(uid: $uid, type: VOICE, format: "amr", body: $body, duration: $duration)
}"""


def voice_duration(body: str) -> int:
    """Validate the container and derive duration from 20 ms AMR-NB frames."""
    if len(body) > 14936:
        raise ValueError("Voice message exceeds 11.2 KB")
    try:
        audio = base64.b64decode(body, validate=True)
    except (ValueError, binascii.Error) as err:
        raise ValueError("Invalid base64 voice data") from err
    if not audio.startswith(b"#!AMR\n") or len(audio) > 11200:
        raise ValueError("Expected an AMR-NB recording below 11.2 KB")
    sizes = (12, 13, 15, 17, 19, 20, 26, 31, 5)
    offset, frames = 6, 0
    while offset < len(audio):
        header = audio[offset]
        mode = (header >> 3) & 15
        if header & 0x83 or mode >= len(sizes):
            raise ValueError("Invalid AMR-NB frame")
        offset += 1 + sizes[mode]
        frames += 1
    if offset != len(audio) or not 50 <= frames <= 750:
        raise ValueError("Record between 1 and 15 seconds")
    return math.ceil(frames / 50)


async def async_send_voice(coordinator: XploraDataUpdateCoordinator, wuid: str, body: str) -> str:
    """Send a validated recording; an HTTP success alone is insufficient."""
    if wuid not in coordinator._configured_wuids:
        raise ValueError("Unknown watch")
    duration = voice_duration(body)
    result = await coordinator._with_recovery(
        lambda: coordinator.controller._gql_handler.runAuthorizedGqlQuery_a(
            SEND_VOICE, {"uid": wuid, "body": body, "duration": duration}, "SendChatMsg"
        )
    )
    message_id = (result.get("data") or {}).get("sendChatMsg")
    if result.get("errors") or not isinstance(message_id, str) or not message_id:
        raise HomeAssistantError("Xplora did not accept the voice message")
    return message_id
