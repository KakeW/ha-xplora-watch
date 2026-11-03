"""FCM header decoding and per-message failure isolation."""

import base64
import binascii
from unittest.mock import patch

import pytest
from firebase_messaging import FcmPushClient

from custom_components.xplora_watch.push import XploraFcmPushClient, _PushDecodeError


def test_unpadded_crypto_key_and_salt_are_decodable():
    def decode(credentials, key, salt, raw):
        return base64.urlsafe_b64decode(key) + base64.urlsafe_b64decode(salt)

    with patch.object(FcmPushClient, "_decrypt_raw_data", side_effect=decode):
        assert XploraFcmPushClient._decrypt_raw_data({}, "YQ", "Yg", b"") == b"ab"


def test_bad_message_does_not_prevent_next_message():
    client = object.__new__(XploraFcmPushClient)
    with patch.object(FcmPushClient, "_handle_data_message", side_effect=[binascii.Error("Incorrect padding"), "received"]):
        assert client._handle_data_message(object()) is None
        assert client._handle_data_message(object()) == "received"


def test_diagnostic_reports_structure_without_exception_contents():
    client = object.__new__(XploraFcmPushClient)

    def fail(*args):
        return client._decrypt_raw_data({}, "YQ", "Yg", b"PRIVATE_MESSAGE")

    with patch.object(FcmPushClient, "_decrypt_raw_data", side_effect=ValueError("SECRET_KEY")):
        with (
            patch.object(FcmPushClient, "_handle_data_message", side_effect=fail),
            patch("custom_components.xplora_watch.push._LOGGER.warning") as warning,
        ):
            client._handle_data_message(object())
    args = warning.call_args.args
    message = args[0] % args[1:]
    assert "stage=decrypt error=ValueError" in message
    assert "key_bytes=1 salt_bytes=1 body_bytes=15" in message
    assert "SECRET_KEY" not in message
    assert "PRIVATE_MESSAGE" not in message


def test_bad_header_is_distinguished_from_decryption_failure():
    with pytest.raises(_PushDecodeError) as error:
        XploraFcmPushClient._decrypt_raw_data({}, "a", "Yg", b"")
    assert error.value.details[:2] == ("peer_key_base64", "Error")
