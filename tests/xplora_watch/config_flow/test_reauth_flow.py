"""Tests for re-authenticating an existing Xplora config entry."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType

from custom_components.xplora_watch.const import DOMAIN


async def _start_reauth(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
    )


async def test_reauth_prompts_for_password(hass, mock_config_entry_email) -> None:
    result = await _start_reauth(hass, mock_config_entry_email)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_updates_existing_entry_and_keeps_its_id(hass, mock_graphql, mock_config_entry_email) -> None:
    entry = mock_config_entry_email
    entry_id = entry.entry_id
    result = await _start_reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-secret"})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.entry_id == entry_id
    assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_reauth_rejects_invalid_password_without_changing_entry(hass, mock_graphql, mock_config_entry_email, graphql_operations) -> None:
    entry = mock_config_entry_email
    graphql_operations["signInWithEmailOrPhone"] = {"errors": [{"message": "bad credentials"}]}
    result = await _start_reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "wrong"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "pass_invalid"}
    assert entry.data[CONF_PASSWORD] == "secret"
