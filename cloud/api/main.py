from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv

from .server import create_app
from .email_service import create_sendgrid_service
from .logging_utils import install_startup_log_buffer
from .notification_settings import NotificationSettings, load_notification_settings
from ..ai import (
    ConsensusClassifier,
    GeminiImageClassifier,
    OpenAIImageClassifier,
    SimpleThresholdModel,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OK Monitor API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument(
        "--datalake-root",
        default="/mnt/data/datalake",
        help="Directory where captures will be stored",
    )
    parser.add_argument(
        "--classifier",
        choices=["simple", "openai", "gemini", "consensus"],
        default="simple",
        help="Classifier backend to use for inference",
    )
    parser.add_argument(
        "--primary-backend",
        choices=["simple", "openai", "gemini"],
        default=None,
        help="Override the primary classifier backend (default derived from --classifier)",
    )
    parser.add_argument(
        "--secondary-backend",
        choices=["simple", "openai", "gemini", "none"],
        default=None,
        help="Override the secondary classifier backend (use 'none' to disable)",
    )
    parser.add_argument(
        "--normal-description-path",
        default="/mnt/data/config/normal_description.txt",
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

    if args.classifier == "simple":
        primary_default = "simple"
        secondary_default = None
    elif args.classifier == "openai":
        primary_default = "openai"
        secondary_default = None
    elif args.classifier == "gemini":
        primary_default = "gemini"
        secondary_default = None
    else:  # consensus
        primary_default = "openai"
        secondary_default = "gemini"

    primary_kind = args.primary_backend or primary_default
    secondary_kind = args.secondary_backend or secondary_default
    if secondary_kind == "none":
        secondary_kind = None

    def build_classifier(kind: str, role: str):
        if kind == "simple":
            return SimpleThresholdModel()
        if kind == "openai":
            key = os.environ.get(args.openai_api_key_env)
            if not key:
                parser.error(
                    f"Environment variable {args.openai_api_key_env} must be set for the {role} OpenAI classifier"
                )
            return OpenAIImageClassifier(
                api_key=key,
                model=args.openai_model,
                base_url=args.openai_base_url,
                normal_description=normal_description,
                timeout=args.openai_timeout,
            )
        if kind == "gemini":
            key = os.environ.get(args.gemini_api_key_env)
            if not key:
                parser.error(
                    f"Environment variable {args.gemini_api_key_env} must be set for the {role} Gemini classifier"
                )
            return GeminiImageClassifier(
                api_key=key,
                model=args.gemini_model,
                base_url=args.gemini_base_url,
                timeout=args.gemini_timeout,
                normal_description=normal_description,
            )
        parser.error(f"Unsupported classifier backend '{kind}' for {role}")

    primary_classifier = build_classifier(primary_kind, "primary")
    secondary_classifier = (
        build_classifier(secondary_kind, "secondary") if secondary_kind else None
    )

    if secondary_classifier is not None:
        classifier = ConsensusClassifier(
            primary=primary_classifier,
            secondary=secondary_classifier,
            primary_label="Agent1",
            secondary_label="Agent2",
        )
    else:
        classifier = primary_classifier

    logger.info(
        "Classifier configuration primary=%s secondary=%s",
        primary_kind,
        secondary_kind or "none",
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

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        timeout_graceful_shutdown=1,  # Only wait 1 second for connections to close
    )
    config.install_signal_handlers = False
    server = uvicorn.Server(config)

    async def _serve() -> None:
        loop = asyncio.get_running_loop()
        shutdown_event: asyncio.Event | None = getattr(
            app.state, "shutdown_event", None
        )
        if shutdown_event is None:
            shutdown_event = asyncio.Event()
            app.state.shutdown_event = shutdown_event

        closing_started = False
        shutdown_count = 0

        async def _close_streams() -> None:
            nonlocal closing_started
            if closing_started:
                return
            closing_started = True
            for name in ("trigger_hub", "capture_hub"):
                hub = getattr(app.state, name, None)
                if hub is None:
                    continue
                try:
                    await hub.close()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to close %s: %s", name, exc)

        def _handle_signal(signum, frame) -> None:  # pragma: no cover - signal handler
            nonlocal shutdown_count
            shutdown_count += 1
            if shutdown_count == 1:
                logger.info("Signal %s received; initiating graceful shutdown (press Ctrl-C again to force).", signum)
                shutdown_event.set()
                server.should_exit = True
                loop.call_soon_threadsafe(lambda: loop.create_task(_close_streams()))
            elif shutdown_count == 2:
                logger.warning("Second signal received; forcing immediate exit.")
                server.force_exit = True
                # Cancel all running tasks
                for task in asyncio.all_tasks(loop):
                    task.cancel()
                # Force stop the event loop
                loop.call_soon_threadsafe(loop.stop)
            else:
                # Third+ signal: nuclear option
                logger.error("Multiple signals received; terminating process immediately.")
                import ctypes
                if hasattr(ctypes, 'windll'):
                    ctypes.windll.kernel32.TerminateProcess(-1, 1)
                else:
                    os._exit(1)

        previous_handlers: dict[int, Any] = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                previous_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, _handle_signal)
            except (AttributeError, ValueError):
                continue

        async def _watch_shutdown() -> None:
            await shutdown_event.wait()
            server.should_exit = True
            await _close_streams()

        watcher_task = loop.create_task(_watch_shutdown())

        try:
            await server.serve()
        finally:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            await _close_streams()
            for sig, handler in previous_handlers.items():
                try:
                    signal.signal(sig, handler)
                except (AttributeError, ValueError):
                    continue
            shutdown_event.set()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received during shutdown")
        pass


if __name__ == "__main__":
    main()
