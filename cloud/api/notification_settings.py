from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class EmailNotificationSettings:
    enabled: bool = False
    recipients: list[str] = field(default_factory=list)

    def sanitized(self) -> "EmailNotificationSettings":
        return EmailNotificationSettings(
            enabled=self.enabled and bool(self.recipients),
            recipients=_clean_recipients(self.recipients),
        )


@dataclass
class NotificationSettings:
    email: EmailNotificationSettings = field(default_factory=EmailNotificationSettings)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "NotificationSettings":
        email_payload = payload.get("email") if isinstance(payload, dict) else None
        email_settings = EmailNotificationSettings()
        if isinstance(email_payload, dict):
            enabled = bool(email_payload.get("enabled"))
            recipients_raw = email_payload.get("recipients", [])
            recipients = _clean_recipients(recipients_raw if isinstance(recipients_raw, list) else [])
            email_settings = EmailNotificationSettings(enabled=enabled and bool(recipients), recipients=recipients)
        return cls(email=email_settings)

    def sanitized(self) -> "NotificationSettings":
        return NotificationSettings(email=self.email.sanitized())


def _clean_recipients(recipients: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for entry in recipients:
        if entry is None:
            continue
        value = str(entry).strip()
        if not value:
            continue
        lower = value.lower()
        if lower in seen:
            continue
        seen.add(lower)
        cleaned.append(value)
    return cleaned


def load_notification_settings(path: Path | None) -> NotificationSettings:
    if path is None or not path.exists():
        return NotificationSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return NotificationSettings()
    return NotificationSettings.from_dict(data).sanitized()


def save_notification_settings(path: Path, settings: NotificationSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = settings.sanitized().to_dict()
    path.write_text(json.dumps(serialized, indent=2, sort_keys=True), encoding="utf-8")


__all__ = [
    "EmailNotificationSettings",
    "NotificationSettings",
    "load_notification_settings",
    "save_notification_settings",
]

