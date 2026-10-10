"""Key material for issuer-bound authority: ed25519 signing keys and named secrets, supplied from OUTSIDE the code.

Two providers, and the difference between them is recorded in every key they hand out (``key_class``):

* :class:`EphemeralKeyProvider` -- ``test`` class.  Keys live in process memory and die with it.  A ``production``
  ledger refuses every ``test`` key, so a test key can never silently become a trusted production key.
* :class:`DirectoryKeyProvider` -- ``production`` class.  Reads PKCS#8 PEM private keys (``<name>.ed25519.pem``) and raw
  secrets (``<name>.secret``) from a directory the OPERATOR supplies.  It refuses a directory inside the repository
  checkout (private material is never committed) and any file readable by group or others.  :func:`generate_key_files`
  is the explicit operator tool that writes them (mode 0600); nothing generates production keys implicitly.

Public verification material is the raw 32-byte ed25519 public key (hex); a key id is its sha256.  The optional
``[authority]`` extra (``cryptography``) provides ed25519; without it every signing or verification REFUSES
(:class:`AuthorityUnavailable`) -- nothing falls back to an unsigned path.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import secrets as _secrets
import stat
from dataclasses import dataclass, field
from typing import Protocol

KEY_CLASSES = ("test", "production")


class AuthorityRefused(ValueError):
    """An authority operation that would admit what it cannot verify."""


class AuthorityUnavailable(AuthorityRefused):
    """The optional ``cryptography`` dependency (the ``[authority]`` extra) is missing."""


def _probe_crypto() -> tuple[object, object, str]:
    """The ``cryptography`` modules, or the recorded absence (declared optional: ``pip install crafty[authority]``)."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ModuleNotFoundError as exc:
        return None, None, repr(exc)
    return ed25519, serialization, ""


def _crypto() -> tuple[object, object]:
    ed25519, serialization, absent = _probe_crypto()
    if ed25519 is None:
        raise AuthorityUnavailable(f"issuer-bound authority needs the optional [authority] extra (cryptography): {absent}")
    return ed25519, serialization


def _ed25519():
    return _crypto()[0]


def key_id_of(public_hex: str) -> str:
    """The identity of a public key: sha256 of its raw bytes."""
    return hashlib.sha256(bytes.fromhex(public_hex)).hexdigest()


def verify_signature(public_hex: str, signature_hex: str, message: bytes) -> bool:
    """True only for a valid ed25519 signature by ``public_hex`` over ``message``.  Malformed input is False."""
    ed = _ed25519()
    try:
        ed.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(signature_hex), message)
    except Exception:                            # noqa: BLE001 - InvalidSignature, bad hex, bad length: all "not valid"
        return False
    return True


@dataclass(frozen=True)
class Signer:
    """A private signing key held by its owner.  ``public_hex`` / ``key_id`` are the verification material."""

    name: str
    key_class: str
    public_hex: str
    _private: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.key_class not in KEY_CLASSES:
            raise AuthorityRefused(f"key class is one of {KEY_CLASSES}")

    @property
    def key_id(self) -> str:
        return key_id_of(self.public_hex)

    def sign(self, message: bytes) -> str:
        return self._private.sign(message).hex()  # type: ignore[attr-defined]


def _signer_from_private(name: str, key_class: str, private: object) -> Signer:
    serialization = _crypto()[1]
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)  # type: ignore[attr-defined]
    return Signer(name, key_class, raw.hex(), private)


class KeyProvider(Protocol):
    key_class: str

    def signer(self, name: str) -> Signer: ...

    def secret(self, name: str) -> bytes: ...


class EphemeralKeyProvider:
    """TEST key material: generated on first use, held in memory, never persisted.  ``key_class == "test"``."""

    key_class = "test"

    def __init__(self) -> None:
        self._signers: dict[str, Signer] = {}
        self._secrets: dict[str, bytes] = {}

    def signer(self, name: str) -> Signer:
        if name not in self._signers:
            self._signers[name] = _signer_from_private(name, "test", _ed25519().Ed25519PrivateKey.generate())
        return self._signers[name]

    def new_signer(self, name: str) -> Signer:
        """A FRESH key under ``name`` (for rotation tests): the old one is dropped from this provider."""
        self._signers[name] = _signer_from_private(name, "test", _ed25519().Ed25519PrivateKey.generate())
        return self._signers[name]

    def secret(self, name: str) -> bytes:
        if name not in self._secrets:
            self._secrets[name] = _secrets.token_bytes(32)
        return self._secrets[name]


def _repository_root() -> pathlib.Path | None:
    """The checkout this package was imported from (the directory holding ``pyproject.toml`` above ``src/engcore``)."""
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "engcore").is_dir():
            return parent
    return None


def _check_private_path(path: pathlib.Path, what: str) -> None:
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise AuthorityRefused(f"{what} {path} is readable or writable by group/others (mode {oct(mode & 0o777)}); "
                               "private key material must be owner-only")


class DirectoryKeyProvider:
    """PRODUCTION key material from an operator-supplied directory outside the repository (``key_class == "production"``)."""

    key_class = "production"

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        d = pathlib.Path(directory).resolve()
        if not d.is_dir():
            raise AuthorityRefused(f"key directory {d} does not exist")
        repo = _repository_root()
        if repo is not None and (d == repo or repo in d.parents):
            raise AuthorityRefused(f"key directory {d} is inside the repository checkout {repo}: private key material "
                                   "is never kept where it can be committed")
        _check_private_path(d, "key directory")
        self._dir = d

    def signer(self, name: str) -> Signer:
        serialization = _crypto()[1]
        path = self._dir / f"{name}.ed25519.pem"
        if not path.is_file():
            raise AuthorityRefused(f"no signing key {name!r} in {self._dir}")
        _check_private_path(path, "signing key")
        private = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(private, _ed25519().Ed25519PrivateKey):
            raise AuthorityRefused(f"{path} is not an ed25519 private key")
        return _signer_from_private(name, "production", private)

    def secret(self, name: str) -> bytes:
        path = self._dir / f"{name}.secret"
        if not path.is_file():
            raise AuthorityRefused(f"no secret {name!r} in {self._dir}")
        _check_private_path(path, "secret")
        data = path.read_bytes()
        if len(data) < 32:
            raise AuthorityRefused(f"secret {name!r} is shorter than 32 bytes")
        return data


def generate_key_files(directory: str | os.PathLike[str], name: str, *, secret: bool = False) -> str:
    """OPERATOR TOOL: write a new ed25519 key (and optionally a secret) as 0600 files; returns the public key hex.
    Refuses to overwrite and refuses a directory inside the repository."""
    serialization = _crypto()[1]
    d = pathlib.Path(directory).resolve()
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    DirectoryKeyProvider(d)                       # the same placement checks the reader applies
    key_path = d / f"{name}.ed25519.pem"
    if key_path.exists():
        raise AuthorityRefused(f"{key_path} exists; keys are never overwritten (rotate instead)")
    private = _ed25519().Ed25519PrivateKey.generate()
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    if secret:
        sfd = os.open(d / f"{name}.secret", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(sfd, "wb") as fh:
            fh.write(_secrets.token_bytes(32))
    return _signer_from_private(name, "production", private).public_hex


__all__ = ["KEY_CLASSES", "AuthorityRefused", "AuthorityUnavailable", "DirectoryKeyProvider", "EphemeralKeyProvider", "KeyProvider",
           "Signer", "generate_key_files", "key_id_of", "verify_signature"]
