"""FCM header decoding and per-message failure isolation."""

import base64
import binascii
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import http_ece
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
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


@pytest.mark.parametrize("signing_first", [False, True])
@pytest.mark.parametrize("padded", [False, True])
def test_combined_crypto_header_delivers_real_encrypted_message(signing_first, padded):
    receiver_key = ec.generate_private_key(ec.SECP256R1())
    sender_key = ec.generate_private_key(ec.SECP256R1())

    def encode(value):
        result = base64.urlsafe_b64encode(value).decode()
        return result if padded else result.rstrip("=")

    def public(key):
        return key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    salt, secret = os.urandom(16), os.urandom(16)
    encrypted = http_ece.encrypt(
        b'{"data":{"content":"test"}}', salt=salt, private_key=sender_key, dh=public(receiver_key), auth_secret=secret, version="aesgcm"
    )
    dh = "dh=" + encode(public(sender_key))
    signing = "p256ecdsa=" + encode(public(sender_key))
    crypto = signing + ";" + dh if signing_first else dh + ";" + signing
    client = object.__new__(XploraFcmPushClient)
    client.credentials = {
        "keys": {
            "private": encode(receiver_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())),
            "secret": encode(secret),
        },
        "gcm": {"app_id": "test-app"},
    }
    client.callback = MagicMock()
    client.callback_context = None
    client._log_verbose = MagicMock()
    client._reset_error_count = MagicMock()
    message = SimpleNamespace(
        stream_id=1,
        last_stream_id_received=0,
        status=0,
        persistent_id="test",
        raw_data=encrypted,
        app_data=[
            SimpleNamespace(key=key, value=value)
            for key, value in [("crypto-key", crypto), ("encryption", "salt=" + encode(salt) + ";rs=4096"), ("subtype", "test-app")]
        ],
    )
    client._handle_data_message(message)
    client.callback.assert_called_once_with({"data": {"content": "test"}}, "test", None)
