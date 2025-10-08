from __future__ import annotations

import argparse
import os
import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .server import create_app
from .email_service import create_sendgrid_service
from .logging_utils import install_startup_log_buffer
from .notification_settings import NotificationSettings, load_notification_settings
from ..ai import ConsensusClassifier, GeminiImageClassifier, OpenAIImageClassifier

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OK Monitor API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument(
        "--datalake-root",
        default="cloud_datalake",
        help="Directory where captures will be stored",
    )
    parser.add_argument(
        "--classifier",
        choices=["simple", "openai", "gemini", "consensus"],
        default="simple",
        help="Classifier backend to use for inference",
    )
    parser.add_argument(
        "--normal-description-path",
        default=None,
        help="Text file describing a normal capture (used by AI classifiers and UI)",
    )
    parser.add_argument(
        "--openai-model",
        default="gpt-4o-mini",
        help="OpenAI model identifier for classification",
    )
    parser.add_argument(
        "--openai-base-url",
        default="https://api.openai.com/v1",
        help="Base URL for the OpenAI API",
    )
    parser.add_argument(
        "--openai-timeout",
        type=float,
        default=30.0,
        help="Timeout (seconds) for OpenAI API requests",
    )
    parser.add_argument(
        "--openai-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable containing the OpenAI API key",
    )
    parser.add_argument(
        "--gemini-model",
        default="models/gemini-2.5-flash",
        help="Gemini model identifier for classification",
    )
    parser.add_argument(
        "--gemini-base-url",
        default="https://generativelanguage.googleapis.com/v1beta",
        help="Base URL for the Gemini API",
    )
    parser.add_argument(
        "--gemini-timeout",
        type=float,
        default=30.0,
        help="Timeout (seconds) for Gemini API requests",
    )
    parser.add_argument(
        "--gemini-api-key-env",
        default="GEMINI_API_KEY",
        help="Environment variable containing the Gemini API key",
    )
    parser.add_argument(
        "--device-id",
        default="ui-device",
        help="Device identifier exposed via the configuration endpoint",
    )
    parser.add_argument(
        "--dedupe-enabled",
        action="store_true",
        help="Enable suppression of repeated identical capture states",
    )
    parser.add_argument(
        "--dedupe-threshold",
        type=int,
        default=3,
        help="Number of identical consecutive states before dedupe kicks in",
    )
    parser.add_argument(
        "--dedupe-keep-every",
        type=int,
        default=5,
        help="After threshold is exceeded, store one capture every N repeats",
    )
    parser.add_argument(
        "--similarity-enabled",
        action="store_true",
        help="Reuse previous classification when images are nearly identical",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=int,
        default=6,
        help="Maximum Hamming distance between perceptual hashes to reuse a classification",
    )
    parser.add_argument(
        "--similarity-expiry-minutes",
        type=float,
        default=60.0,
        help="Expiry window (minutes) for cached similarity entries (0 to disable)",
    )
    parser.add_argument(
        "--similarity-cache-path",
        default="config/similarity_cache.json",
        help="Path to the similarity cache persistence file",
    )
    parser.add_argument(
        "--streak-pruning-enabled",
        action="store_true",
        help="Enable streak-based image pruning after repeated identical states",
    )
    parser.add_argument(
        "--streak-threshold",
        type=int,
        default=10,
        help="Number of identical states before image pruning starts",
    )
    parser.add_argument(
        "--streak-keep-every",
        type=int,
        default=5,
        help="After pruning starts, retain one image every N captures",
    )
    parser.add_argument(
        "--sendgrid-api-key-env",
        default="SENDGRID_API_KEY",
        help="Environment variable containing the SendGrid API key",
    )
    parser.add_argument(
        "--alert-from-email-env",
        default="ALERT_FROM_EMAIL",
        help="Environment variable containing the alert sender email",
    )
    parser.add_argument(
        "--notification-config-path",
        default="config/notifications.json",
        help="Path to the JSON file storing notification preferences",
    )
    parser.add_argument(
        "--alert-environment-label-env",
        default="ALERT_ENVIRONMENT_LABEL",
        help="Environment variable holding an optional environment label for alert subjects",
    )
    return parser


def main() -> None:
    load_dotenv()
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
        )
    parser = build_parser()
    install_startup_log_buffer()
    args = parser.parse_args()

    description_path: Path | None = None
    normal_description = ""
    if args.normal_description_path:
        description_path = Path(args.normal_description_path)
        if description_path.exists():
            try:
                normal_description = description_path.read_text(encoding="utf-8")
            except OSError as exc:
                parser.error(f"Failed to read normal description file: {exc}")

    description_store_dir = (
        description_path.parent
        if description_path is not None
        else Path("config/normal_descriptions")
    )

    classifier = None
    openai_client = None
    gemini_client = None
    if args.classifier in {"openai", "consensus"}:
        openai_key = os.environ.get(args.openai_api_key_env)
        if not openai_key:
            parser.error(
                f"Environment variable {args.openai_api_key_env} must be set to use the OpenAI classifier"
            )
        openai_client = OpenAIImageClassifier(
            api_key=openai_key,
            model=args.openai_model,
            base_url=args.openai_base_url,
            normal_description=normal_description,
            timeout=args.openai_timeout,
        )

    if args.classifier in {"gemini", "consensus"}:
        gemini_key = os.environ.get(args.gemini_api_key_env)
        if not gemini_key:
            parser.error(
                f"Environment variable {args.gemini_api_key_env} must be set to use the Gemini classifier"
            )
        gemini_client = GeminiImageClassifier(
            api_key=gemini_key,
            model=args.gemini_model,
            base_url=args.gemini_base_url,
            timeout=args.gemini_timeout,
            normal_description=normal_description,
        )

    if args.classifier == "openai":
        classifier = openai_client
    elif args.classifier == "gemini":
        classifier = gemini_client
    elif args.classifier == "consensus":
        classifier = ConsensusClassifier(
            primary=openai_client,
            secondary=gemini_client,
            primary_label="Agent1",
            secondary_label="Agent2",
        )

    sendgrid_key = os.environ.get(args.sendgrid_api_key_env)
    sender_email = os.environ.get(args.alert_from_email_env)
    environment_label = os.environ.get(args.alert_environment_label_env)

    base_email_kwargs: dict[str, str | None] | None = None
    if sendgrid_key and sender_email:
        base_email_kwargs = {
            "api_key": sendgrid_key,
            "sender": sender_email,
            "environment_label": environment_label or None,
            "ui_base_url": os.environ.get("OK_CLOUD_BASE_URL"),
        }
    elif sendgrid_key or sender_email:
        missing = [
            name
            for name, value in [
                (args.sendgrid_api_key_env, sendgrid_key),
                (args.alert_from_email_env, sender_email),
            ]
            if not value
        ]
        logger.warning(
            "Partial SendGrid configuration detected; missing %s. Email alerts disabled.",
            ", ".join(missing),
        )

    notification_path = Path(args.notification_config_path)
    notification_settings = load_notification_settings(notification_path).sanitized()

    email_service = None
    if notification_settings.email.enabled and not base_email_kwargs:
        logger.warning(
            "Email notifications enabled in %s but SendGrid credentials are missing; disabling alerts.",
            notification_path,
        )
        notification_settings.email.enabled = False

    if (
        base_email_kwargs
        and notification_settings.email.enabled
        and notification_settings.email.recipients
    ):
        try:
            email_service = create_sendgrid_service(
                api_key=base_email_kwargs["api_key"],
                sender=base_email_kwargs["sender"],
                recipients=notification_settings.email.recipients,
                environment_label=base_email_kwargs.get("environment_label"),
                description_root=description_store_dir,
                ui_base_url=base_email_kwargs.get("ui_base_url"),
            )
            logger.info(
                "SendGrid email alerts enabled recipients=%d",
                len(notification_settings.email.recipients),
            )
        except Exception as exc:
            logger.error("Failed to initialise SendGrid client: %s", exc)
            email_service = None

    app = create_app(
        Path(args.datalake_root),
        classifier=classifier,
        normal_description=normal_description,
        normal_description_path=description_path,
        device_id=args.device_id,
        abnormal_notifier=email_service,
        notification_settings=notification_settings,
        notification_config_path=notification_path,
        email_base_config=base_email_kwargs,
        dedupe_enabled=args.dedupe_enabled,
        dedupe_threshold=args.dedupe_threshold,
        dedupe_keep_every=args.dedupe_keep_every,
        similarity_enabled=args.similarity_enabled,
        similarity_threshold=args.similarity_threshold,
        similarity_expiry_minutes=args.similarity_expiry_minutes,
        similarity_cache_path=args.similarity_cache_path,
        streak_pruning_enabled=args.streak_pruning_enabled,
        streak_threshold=args.streak_threshold,
        streak_keep_every=args.streak_keep_every,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
