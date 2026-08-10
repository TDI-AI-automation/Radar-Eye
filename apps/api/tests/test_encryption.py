from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from apps.api.app.security.encryption import (
    CredentialEncryptionProvider,
    FernetCredentialEncryptionProvider,
    get_credential_encryption_provider,
)


def _provider() -> FernetCredentialEncryptionProvider:
    return FernetCredentialEncryptionProvider(Fernet.generate_key().decode())


def test_fernet_provider_is_a_credential_encryption_provider() -> None:
    assert isinstance(_provider(), CredentialEncryptionProvider)


def test_encrypt_then_decrypt_round_trips() -> None:
    provider = _provider()
    plaintext = "rtsp://user:pass@10.0.0.5:554/stream"

    ciphertext = provider.encrypt(plaintext)

    assert ciphertext != plaintext
    assert provider.decrypt(ciphertext) == plaintext


def test_ciphertext_is_not_decryptable_with_a_different_key() -> None:
    provider_a = _provider()
    provider_b = _provider()

    ciphertext = provider_a.encrypt("rtsp://camera-1/stream")

    try:
        provider_b.decrypt(ciphertext)
        raised = False
    except InvalidToken:
        raised = True

    assert raised


def test_factory_builds_provider_from_settings() -> None:
    from apps.api.app.config import get_settings

    settings = get_settings()

    provider = get_credential_encryption_provider(settings)

    assert isinstance(provider, FernetCredentialEncryptionProvider)
    ciphertext = provider.encrypt("rtsp://camera-2/stream")
    assert provider.decrypt(ciphertext) == "rtsp://camera-2/stream"
