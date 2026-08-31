"""Shared credential-name recognition for review-process boundaries."""

from __future__ import annotations

SECRET_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")


def is_secret_name(name: str) -> bool:
    """Return whether an environment-variable name conventionally holds a secret."""
    upper_name = name.upper()
    return any(part in upper_name for part in SECRET_NAME_PARTS)
