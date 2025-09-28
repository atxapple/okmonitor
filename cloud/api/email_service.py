from __future__ import annotations

import json
import logging
import mimetypes
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Protocol, Sequence

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

from ..datalake.storage import CaptureRecord


logger = logging.getLogger(__name__)


class AbnormalCaptureNotifier(Protocol):
    def notify_abnormal(self, record: CaptureRecord) -> None:
        """Dispatch an alert for an abnormal capture."""


@dataclass(frozen=True)
class SendGridEmailConfig:
    api_key: str
    sender: str
    recipients: Sequence[str]
    subject: str = "OK Monitor: Abnormal capture detected"
    environment_label: str | None = None
    ui_base_url: str | None = None


class SendGridEmailService(AbnormalCaptureNotifier):
    def __init__(
        self,
        config: SendGridEmailConfig,
        client: SendGridAPIClient | None = None,
        description_root: Path | None = None,
    ) -> None:
        self._config = config
        self._client = client or SendGridAPIClient(api_key=config.api_key)
        self._description_root = description_root

    def notify_abnormal(self, record: CaptureRecord) -> None:
        message = self._build_message(record)
        try:
            self._client.send(message)
        except Exception:
            logger.exception("SendGrid attempt failed record_id=%s", record.record_id)
            raise

    def _build_message(self, record: CaptureRecord) -> Mail:
        classification = record.classification
        state = classification.get("state")
        reason = classification.get("reason") or "No reason supplied."
        score = classification.get("score")
        metadata = record.metadata
        sent_at = datetime.now(timezone.utc).isoformat()
        subject = self._render_subject(record)
        normal_description = self._load_normal_description(record)
        image_cid = f"capture-{record.record_id}" if record.image_path.exists() else None
        capture_url = self._build_capture_url(record)
        plain = self._render_plain(
            subject,
            metadata,
            state,
            score,
            reason,
            record,
            sent_at,
            normal_description,
            capture_url,
        )
        html = self._render_html(
            subject,
            metadata,
            state,
            score,
            reason,
            record,
            sent_at,
            normal_description,
            image_cid,
            capture_url,
        )
        mail = Mail(
            from_email=self._config.sender,
            to_emails=list(self._config.recipients),
            subject=subject,
            plain_text_content=plain,
            html_content=html,
        )
        if image_cid is not None:
            attachment = self._build_inline_image(record, image_cid)
            if attachment is not None:
                mail.add_attachment(attachment)
        return mail

    def _render_subject(self, record: CaptureRecord) -> str:
        parts = [self._config.subject]
        device = record.metadata.get("device_id")
        if device:
            parts.append(f"device={device}")
        if self._config.environment_label:
            parts.append(self._config.environment_label)
        return " ".join(parts)

    def _render_plain(
        self,
        subject: str,
        metadata: dict[str, object],
        state: object,
        score: object,
        reason: object,
        record: CaptureRecord,
        sent_at: str,
        normal_description: str | None,
        capture_url: str | None,
    ) -> str:
        payload = {
            "subject": subject,
            "state": state,
            "score": score,
            "reason": reason,
            "record_id": record.record_id,
            "captured_at": record.captured_at.isoformat(),
            "image_path": str(record.image_path),
            "metadata": metadata,
            "sent_at": sent_at,
            "normal_description": normal_description,
            "capture_url": capture_url,
        }
        return json.dumps(payload, indent=2)

    def _render_html(
        self,
        subject: str,
        metadata: dict[str, object],
        state: object,
        score: object,
        reason: object,
        record: CaptureRecord,
        sent_at: str,
        normal_description: str | None,
        image_cid: str | None,
        capture_url: str | None,
    ) -> str:
        metadata_rows = "".join(
            f"<tr><th style='text-align:left;padding-right:12px;'>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
            for key, value in sorted(metadata.items())
        )
        if not metadata_rows:
            metadata_rows = "<tr><td colspan='2'><em>No metadata provided</em></td></tr>"
        score_str = f"{score:.2f}" if isinstance(score, (float, int)) else score
        if normal_description:
            description_html = escape(normal_description)
        else:
            description_html = "<em>No normal description available.</em>"
        image_block = (
            f"<img src='cid:{image_cid}' alt='Abnormal capture image' style='max-width:100%;height:auto;border-radius:8px;' />"
            if image_cid
            else f"<p><strong>Capture file:</strong> {escape(str(record.image_path))}</p>"
        )
        link_block = (
            f"<p style='margin-top:12px;'><a href='{escape(capture_url)}' target='_blank' rel='noopener'>Open in web UI</a></p>"
            if capture_url
            else ""
        )
        return (
            "<html>"
            "  <body>"
            f"    <h2>{escape(subject)}</h2>"
            f"    <p>An abnormal capture was detected at <strong>{escape(record.captured_at.isoformat())}</strong> (UTC).</p>"
            "    <ul>"
            f"      <li><strong>Record ID:</strong> {escape(record.record_id)}</li>"
            f"      <li><strong>State:</strong> {escape(str(state))}</li>"
            f"      <li><strong>Confidence score:</strong> {escape(str(score_str))}</li>"
            f"      <li><strong>Reason:</strong> {escape(str(reason))}</li>"
            "    </ul>"
            f"    <div style='margin:16px 0;'>{image_block}</div>"
            "    <h3>Normal Definition</h3>"
            f"    <pre style='background:#f8fafc;padding:12px;border-radius:8px;white-space:pre-wrap;'>{description_html}</pre>"
            "    <h3>Metadata</h3>"
            "    <table style='border-collapse:collapse;'>"
            "      <tbody>"
            f"        {metadata_rows}"
            "      </tbody>"
            "    </table>"
            f"    <p style='margin-top:16px;font-size:12px;color:#555;'>Alert sent at {escape(sent_at)}</p>"
            f"    {link_block}"
            "  </body>"
            "</html>"
        )

    def _load_normal_description(self, record: CaptureRecord) -> str | None:
        file_name = getattr(record, "normal_description_file", None)
        if not file_name:
            return None
        candidates: list[Path] = []
        if self._description_root:
            candidates.append(self._description_root / file_name)
        candidates.append(record.metadata_path.parent / file_name)
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate.read_text(encoding="utf-8")
            except OSError:
                logger.debug("Failed to read normal description file path=%s", candidate)
        return None

    def _build_inline_image(self, record: CaptureRecord, cid: str) -> Attachment | None:
        try:
            data = record.image_path.read_bytes()
        except OSError:
            logger.warning("Unable to read capture image for record_id=%s", record.record_id)
            return None
        if not data:
            return None
        mime_type, _ = mimetypes.guess_type(record.image_path.name)
        if mime_type is None:
            mime_type = "application/octet-stream"
        encoded = b64encode(data).decode("ascii")
        attachment = Attachment()
        attachment.file_content = FileContent(encoded)
        attachment.file_name = FileName(record.image_path.name)
        attachment.file_type = FileType(mime_type)
        attachment.disposition = Disposition("inline")
        attachment.content_id = ContentId(cid)
        return attachment

    def _build_capture_url(self, record: CaptureRecord) -> str | None:
        base = (self._config.ui_base_url or "").strip()
        if not base:
            return None
        base = base.rstrip("/")
        return f"{base}/ui"


__all__ = [
    "AbnormalCaptureNotifier",
    "SendGridEmailConfig",
    "SendGridEmailService",
    "create_sendgrid_service",
]

def create_sendgrid_service(
    *,
    api_key: str,
    sender: str,
    recipients: Sequence[str],
    subject: str | None = None,
    environment_label: str | None = None,
    client: SendGridAPIClient | None = None,
    description_root: Path | None = None,
    ui_base_url: str | None = None,
) -> SendGridEmailService:
    resolved_subject = subject if subject is not None else SendGridEmailConfig.subject
    config = SendGridEmailConfig(
        api_key=api_key,
        sender=sender,
        recipients=list(recipients),
        subject=resolved_subject,
        environment_label=environment_label,
        ui_base_url=ui_base_url,
    )
    return SendGridEmailService(
        config=config,
        client=client,
        description_root=description_root,
    )
