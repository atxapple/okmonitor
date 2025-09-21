from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from .server import create_app
from ..ai import OpenAIImageClassifier


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
        choices=["simple", "openai"],
        default="simple",
        help="Classifier backend to use for inference",
    )
    parser.add_argument(
        "--normal-description-path",
        default=None,
        help="Text file describing a normal capture (used by the OpenAI classifier and UI)",
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
        "--device-id",
        default="ui-device",
        help="Device identifier exposed via the configuration endpoint",
    )
    return parser


def main() -> None:
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
    if args.classifier == "openai":
        api_key = os.environ.get(args.openai_api_key_env)
        if not api_key:
            parser.error(
                f"Environment variable {args.openai_api_key_env} must be set to use the OpenAI classifier"
            )

        classifier = OpenAIImageClassifier(
            api_key=api_key,
            model=args.openai_model,
            base_url=args.openai_base_url,
            normal_description=normal_description,
            timeout=args.openai_timeout,
        )

    app = create_app(
        Path(args.datalake_root),
        classifier=classifier,
        normal_description=normal_description,
        normal_description_path=description_path,
        device_id=args.device_id,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
