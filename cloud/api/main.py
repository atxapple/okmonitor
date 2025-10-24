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

from .config_loader import load_config
from .server import create_app
from .email_service import create_sendgrid_service
from .logging_utils import install_startup_log_buffer
from .notification_settings import NotificationSettings, load_notification_settings
from .persistent_config import load_server_config
from .datalake_pruner import prune_datalake
from ..ai import (
    ConsensusClassifier,
    GeminiImageClassifier,
    OpenAIImageClassifier,
    SimpleThresholdModel,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser with minimal CLI flags.

    Most configuration is now loaded from config/cloud.json.
    CLI flags are only for quick overrides.
    """
    parser = argparse.ArgumentParser(
        description="Run the OK Monitor API server",
        epilog="Configuration is loaded from config/cloud.json. "
               "CLI arguments override config file settings."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/cloud.json",
        help="Path to JSON configuration file (default: config/cloud.json)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override server host (default: from config file)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override server port (default: from config file)"
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

    # Load configuration from JSON file
    try:
        cfg = load_config(args.config if Path(args.config).exists() else None)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {args.config}")
        logger.info("Using default configuration. Copy config/cloud.example.json to config/cloud.json")
        cfg = load_config(None)  # Use defaults
    except Exception as exc:
        logger.error(f"Failed to load configuration: {exc}")
        sys.exit(1)

    # Apply CLI overrides
    if args.host:
        cfg.server.host = args.host
    if args.port:
        cfg.server.port = args.port

    logger.info(f"Server configuration: {cfg.server.host}:{cfg.server.port}")
    logger.info(f"Datalake root: {cfg.storage.datalake_root}")
    logger.info(f"Classifier backend: {cfg.classifier.backend}")

    # Load persistent server configuration to restore active normal description
    server_config_path = Path("/mnt/data/config/server_config.json")
    persistent_config = load_server_config(server_config_path)

    description_path: Path | None = None
    normal_description = ""

    # Check if there's a persisted active normal description file
    if persistent_config.active_normal_description_file:
        store_dir = Path(cfg.paths.normal_description).parent
        persisted_path = store_dir / persistent_config.active_normal_description_file
        if persisted_path.exists():
            try:
                normal_description = persisted_path.read_text(encoding="utf-8")
                description_path = persisted_path
                logger.info(
                    "Restored active normal description from persistent config: %s",
                    persistent_config.active_normal_description_file,
                )
            except OSError as exc:
                logger.warning(
                    "Failed to read persisted normal description %s: %s",
                    persisted_path,
                    exc,
                )

    # Fall back to configured path if no persisted config or load failed
    if not description_path:
        description_path = Path(cfg.paths.normal_description)
        if description_path.exists():
            try:
                normal_description = description_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(f"Failed to read normal description file: {exc}")

    description_store_dir = (
        description_path.parent
        if description_path is not None
        else Path("/mnt/data/config")
    )

    # Determine primary and secondary classifiers
    classifier = None

    if cfg.classifier.backend == "simple":
        primary_default = "simple"
        secondary_default = None
    elif cfg.classifier.backend == "openai":
        primary_default = "openai"
        secondary_default = None
    elif cfg.classifier.backend == "gemini":
        primary_default = "gemini"
        secondary_default = None
    else:  # consensus
        primary_default = "openai"
        secondary_default = "gemini"

    primary_kind = cfg.classifier.primary_backend or primary_default
    secondary_kind = cfg.classifier.secondary_backend or secondary_default
    if secondary_kind == "none":
        secondary_kind = None

    def build_classifier(kind: str, role: str):
        if kind == "simple":
            return SimpleThresholdModel()
        if kind == "openai":
            key = os.environ.get(cfg.classifier.openai.api_key_env)
            if not key:
                logger.error(
                    f"Environment variable {cfg.classifier.openai.api_key_env} must be set for {role} OpenAI classifier"
                )
                sys.exit(1)
            return OpenAIImageClassifier(
                api_key=key,
                model=cfg.classifier.openai.model,
                base_url=cfg.classifier.openai.base_url,
                normal_description=normal_description,
                timeout=cfg.classifier.openai.timeout,
            )
        if kind == "gemini":
            key = os.environ.get(cfg.classifier.gemini.api_key_env)
            if not key:
                logger.error(
                    f"Environment variable {cfg.classifier.gemini.api_key_env} must be set for {role} Gemini classifier"
                )
                sys.exit(1)
            return GeminiImageClassifier(
                api_key=key,
                model=cfg.classifier.gemini.model,
                base_url=cfg.classifier.gemini.base_url,
                timeout=cfg.classifier.gemini.timeout,
                normal_description=normal_description,
            )
        logger.error(f"Unsupported classifier backend '{kind}' for {role}")
        sys.exit(1)

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

    # Email configuration
    sendgrid_key = os.environ.get(cfg.email.sendgrid_api_key_env)
    sender_email = os.environ.get(cfg.email.alert_from_email_env)
    environment_label = os.environ.get(cfg.email.alert_environment_label_env)

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
                (cfg.email.sendgrid_api_key_env, sendgrid_key),
                (cfg.email.alert_from_email_env, sender_email),
            ]
            if not value
        ]
        logger.warning(
            "Partial SendGrid configuration detected; missing %s. Email alerts disabled.",
            ", ".join(missing),
        )

    notification_path = Path(cfg.paths.notification_config)
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

    # Timing debug (can be overridden by environment variable)
    timing_debug_enabled = cfg.features.timing_debug.enabled

    # Run datalake pruning on startup if enabled
    if cfg.features.datalake_pruning.enabled and cfg.features.datalake_pruning.run_on_startup:
        logger.info("Running datalake pruning on startup...")
        try:
            stats = prune_datalake(
                Path(cfg.storage.datalake_root),
                cfg.features.datalake_pruning.retention_days,
                dry_run=False,
            )
            logger.info(
                f"Startup pruning complete: deleted={stats.images_deleted}, "
                f"freed={stats.bytes_freed:,} bytes, errors={stats.errors}"
            )
        except Exception as exc:
            logger.error(f"Startup pruning failed: {exc}")

    # Create FastAPI app
    app = create_app(
        Path(cfg.storage.datalake_root),
        classifier=classifier,
        normal_description=normal_description,
        normal_description_path=description_path,
        device_id="ui-device",  # Default device ID for single-tenant
        abnormal_notifier=email_service,
        notification_settings=notification_settings,
        notification_config_path=notification_path,
        email_base_config=base_email_kwargs,
        dedupe_enabled=cfg.features.dedupe.enabled,
        dedupe_threshold=cfg.features.dedupe.threshold,
        dedupe_keep_every=cfg.features.dedupe.keep_every,
        similarity_enabled=cfg.features.similarity.enabled,
        similarity_threshold=cfg.features.similarity.threshold,
        similarity_expiry_minutes=cfg.features.similarity.expiry_minutes,
        similarity_cache_path=cfg.features.similarity.cache_path,
        streak_pruning_enabled=cfg.features.streak_pruning.enabled,
        streak_threshold=cfg.features.streak_pruning.threshold,
        streak_keep_every=cfg.features.streak_pruning.keep_every,
        timing_debug_enabled=timing_debug_enabled,
        timing_debug_max_captures=cfg.features.timing_debug.max_captures,
    )

    # Start uvicorn server
    config = uvicorn.Config(
        app,
        host=cfg.server.host,
        port=cfg.server.port,
        log_level="info",
        timeout_graceful_shutdown=1,
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

        async def _periodic_pruning() -> None:
            """Run datalake pruning periodically if enabled."""
            if not cfg.features.datalake_pruning.enabled:
                return

            interval_hours = cfg.features.datalake_pruning.run_interval_hours
            interval_seconds = interval_hours * 3600

            while not shutdown_event.is_set():
                try:
                    # Wait for the interval or shutdown
                    await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
                    break  # Shutdown was triggered
                except asyncio.TimeoutError:
                    # Interval elapsed, run pruning
                    logger.info("Running periodic datalake pruning...")
                    try:
                        stats = prune_datalake(
                            Path(cfg.storage.datalake_root),
                            cfg.features.datalake_pruning.retention_days,
                            dry_run=False,
                        )
                        logger.info(
                            f"Periodic pruning complete: deleted={stats.images_deleted}, "
                            f"freed={stats.bytes_freed:,} bytes, errors={stats.errors}"
                        )
                    except Exception as exc:
                        logger.error(f"Periodic pruning failed: {exc}")

        watcher_task = loop.create_task(_watch_shutdown())
        pruning_task = loop.create_task(_periodic_pruning())

        try:
            await server.serve()
        finally:
            watcher_task.cancel()
            pruning_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            with contextlib.suppress(asyncio.CancelledError):
                await pruning_task
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
