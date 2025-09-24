from __future__ import annotations

import argparse
import os
import logging
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .server import create_app
from ..ai import ConsensusClassifier, GeminiImageClassifier, OpenAIImageClassifier


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
    return parser


def main() -> None:
    load_dotenv()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    parser = build_parser()
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
            primary_label="OpenAI",
            secondary_label="Gemini",
        )

    app = create_app(
        Path(args.datalake_root),
        classifier=classifier,
        normal_description=normal_description,
        normal_description_path=description_path,
        device_id=args.device_id,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
