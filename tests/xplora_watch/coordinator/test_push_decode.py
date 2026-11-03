"""FCM header decoding and per-message failure isolation."""

import base64
import binascii
from unittest.mock import patch

from firebase_messaging import FcmPushClient

from custom_components.xplora_watch.push import XploraFcmPushClient


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
