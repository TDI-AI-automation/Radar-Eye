"""Credential encryption abstraction.

Source: RM-03 design review — the architecture depends only on
``CredentialEncryptionProvider``, never on a concrete algorithm, so the
implementation can be swapped (e.g. for a KMS-backed provider later) without
touching repository or persistence code. ``FernetCredentialEncryptionProvider``
is the initial concrete implementation.

The encryption key comes exclusively from an environment variable
(``RADAR_EYE_ENCRYPTION_KEY``, see ``apps.api.app.config.EnvSettings``) --
never from ``configs/settings.yaml`` or any other repository file.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet

if TYPE_CHECKING:
    from apps.api.app.config import Settings


class CredentialEncryptionProvider(ABC):
    """Encrypts/decrypts credentials (e.g. RTSP URLs) at rest."""

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return an opaque, storable ciphertext for ``plaintext``."""

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Recover the original plaintext from ``ciphertext``."""


class FernetCredentialEncryptionProvider(CredentialEncryptionProvider):
    """Symmetric, authenticated encryption via ``cryptography``'s Fernet."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def get_credential_encryption_provider(settings: Settings) -> CredentialEncryptionProvider:
    """Build the configured ``CredentialEncryptionProvider`` from settings."""
    return FernetCredentialEncryptionProvider(settings.encryption_key.get_secret_value())
