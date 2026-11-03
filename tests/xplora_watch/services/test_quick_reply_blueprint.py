"""Execute the shipped notification blueprint through HA's script engine."""

from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import template
from homeassistant.helpers.script import Script
from homeassistant.util import yaml as yaml_util


def blueprint_config():
    path = Path(__file__).resolve().parents[3] / "blueprints/automation/xplora_message_quick_reply.yaml"
    data = yaml_util.load_yaml(str(path))
    blueprint = Blueprint(data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    return yaml_util.substitute(blueprint.data, {"phone": "phone-device", "watches": ["ellie", "lilian"]})


@pytest.mark.parametrize("watch", ["ellie", "lilian"])
async def test_reply_routes_text_to_the_right_watch(hass, watch):
    config = blueprint_config()
    calls = []
    hass.services.async_register("xplora_watch", "send_message", lambda call: calls.append(call.data))
    script = Script(hass, cv.SCRIPT_SCHEMA(config["actions"]), "Quick reply", "automation")
    await script.async_run(
        {
            "watches": ["ellie", "lilian"],
            "phone": "phone-device",
            "trigger": {
                "id": "reply",
                "event": {"data": {"action": "XPLORA_REPLY_phone-device:" + watch, "reply_text": "Tulossa!"}},
            },
        }
    )
    assert calls == [{"device_id": watch, "message": "Tulossa!"}]


@pytest.mark.parametrize(
    "action,text",
    [
        ("XPLORA_REPLY_phone-device:other", "Hi"),
        ("OTHER_ellie", "Hi"),
        ("XPLORA_REPLY_phone-device:ellie", "  "),
        ("XPLORA_REPLY_other-phone:ellie", "Hi"),
    ],
)
async def test_unselected_watch_or_empty_reply_does_not_send(hass, action, text):
    config = blueprint_config()
    calls = []
    hass.services.async_register("xplora_watch", "send_message", lambda call: calls.append(call.data))
    script = Script(hass, cv.SCRIPT_SCHEMA(config["actions"]), "Quick reply", "automation")
    await script.async_run(
        {
            "watches": ["ellie", "lilian"],
            "phone": "phone-device",
            "trigger": {
                "id": "reply",
                "event": {"data": {"action": action, "reply_text": text}},
            },
        }
    )
    assert calls == []


async def test_incoming_notification_contains_background_text_action(hass):
    config = blueprint_config()
    calls = []

    async def notify(hass, action, variables, context):
        assert action["device_id"] == "phone-device"
        data = cv.template_complex(action["data"])
        calls.append({"data": template.render_complex(data, variables)})

    script = Script(hass, cv.SCRIPT_SCHEMA(config["actions"]), "Quick reply", "automation")
    with (
        patch("homeassistant.helpers.script.device_action.async_call_action_from_config", side_effect=notify),
    ):
        await script.async_run(
            {
                "watches": ["ellie", "lilian"],
                "phone": "phone-device",
                "trigger": {
                    "id": "incoming",
                    "event": {
                        "data": {
                            "device_id": "lilian",
                            "message_id": "123",
                            "sender_name": "Lilian",
                            "text": "Moi!",
                        }
                    },
                },
            }
        )
    assert len(calls) == 1
    action = calls[0]["data"]["actions"][0]
    assert action["action"] == "XPLORA_REPLY_phone-device:lilian"
    assert action["behavior"] == "textInput"
    assert action["activationMode"] == "background"
