from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .server import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OK Monitor API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument(
        "--datalake-root",
        default="cloud_datalake",
        help="Directory where captures will be stored",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    app = create_app(Path(args.datalake_root))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()