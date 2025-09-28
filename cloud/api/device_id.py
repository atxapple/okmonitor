from __future__ import annotations

"""Utilities for working with device identifiers."""

_ALLOWED_CHARS = {"-", "_", "."}


def sanitize_device_id(raw: str | None) -> str:
    """Validate and normalise a device identifier.

    Whitespace is stripped and the identifier must contain at least one character.
    Only alphanumeric characters plus ``-``, ``_`` and ``.`` are permitted.
    """

    if raw is None:
        raise ValueError("Device ID is required")

    candidate = raw.strip()
    if not candidate:
        raise ValueError("Device ID cannot be empty")

    for character in candidate:
        if character.isalnum():
            continue
        if character not in _ALLOWED_CHARS:
            raise ValueError(
                "Device ID may only contain letters, numbers, dashes, underscores, or periods",
            )

    return candidate


__all__ = ["sanitize_device_id"]
