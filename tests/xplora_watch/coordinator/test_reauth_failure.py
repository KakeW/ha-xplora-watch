"""Authentication failures request Home Assistant's credential reauth flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.xplora_watch.pyxplora_api.exception_classes import LoginError


async def test_failed_token_recovery_surfaces_config_entry_auth_failed(coordinator) -> None:
    """A terminal login failure must prompt for credentials, not just retry forever."""
    assert coordinator.config_entry is coordinator._entry
    with patch.object(coordinator, "_with_recovery", new=AsyncMock(side_effect=LoginError("bad password"))):
        with pytest.raises(ConfigEntryAuthFailed, match="Xplora authentication failed"):
            await coordinator._fetch_and_store_xplora_data(None, force_functions=False, include_chats=False)
