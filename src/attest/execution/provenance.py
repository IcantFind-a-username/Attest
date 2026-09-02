"""Controller provenance seal for evidence bundles (V-03).

The controller holds a secret key that no executor mount ever contains
(``.attest/controller.key`` lives beside the ledger, outside every tree,
inputs and outputs directory). After a bundle is written the controller seals
the manifest digest and the receipt's provenance digest with HMAC-SHA256; an
offline verifier holding the key recomputes the manifest digest from the files
and rejects any bundle whose seal does not match, was copied from another
bundle, or is missing. Without the key the verifier reports the seal as
unverified and, when asked to require it, rejects.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

PROVENANCE_SCHEMA_VERSION = "attest.provenance-seal.v1"
ALGORITHM = "HMAC-SHA256"
KEY_RELATIVE = Path(".attest") / "controller.key"
KEY_BYTES = 32


def key_id(key: bytes) -> str:
    return hashlib.sha256(b"attest-controller-key:" + key).hexdigest()[:16]


def load_or_create_key(repo: Path) -> bytes:
    """The repository's controller key, created on first use with mode 0600."""
    path = repo / KEY_RELATIVE
    try:
        data = path.read_bytes()
    except OSError:
        data = b""
    if len(data) == KEY_BYTES:
        return data
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = secrets.token_bytes(KEY_BYTES)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(fresh)
    return fresh


def load_key(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) != KEY_BYTES:
        raise ValueError(f"controller key {path} must be {KEY_BYTES} bytes")
    return data


def _message(manifest_digest: str, receipt_digest: str) -> bytes:
    return json.dumps(
        {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "manifest_digest": manifest_digest,
            "receipt_digest": receipt_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def seal(manifest_digest: str, receipt_digest: str, key: bytes) -> dict[str, Any]:
    signature = hmac.new(key, _message(manifest_digest, receipt_digest), hashlib.sha256)
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "key_id": key_id(key),
        "manifest_digest": manifest_digest,
        "receipt_digest": receipt_digest,
        "signature": signature.hexdigest(),
    }


def verify_seal(
    value: object, manifest_digest: str, receipt_digest: str, key: bytes
) -> tuple[str, ...]:
    """Every reason the seal does not authenticate this bundle; empty when it does."""
    if not isinstance(value, dict):
        return ("seal missing or malformed",)
    reasons: list[str] = []
    if value.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        reasons.append("unknown seal schema")
    if value.get("algorithm") != ALGORITHM:
        reasons.append("unknown seal algorithm")
    if value.get("key_id") != key_id(key):
        reasons.append("seal was made with a different controller key")
    if value.get("manifest_digest") != manifest_digest:
        reasons.append("seal names a different bundle manifest")
    if value.get("receipt_digest") != receipt_digest:
        reasons.append("seal names a different receipt")
    signature = value.get("signature")
    expected = hmac.new(key, _message(manifest_digest, receipt_digest), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        reasons.append("seal signature does not verify")
    return tuple(reasons)
