#!/usr/bin/env python3
"""
Simple smoke tester for NVIDIA NIM (OpenAI-compatible) vision models.

Usage:
    python scripts/nim_smoke_test.py --image path/to/image.jpg

Environment variables:
    NVIDIA_API_KEY       - required bearer token for the NIM service
    NVIDIA_NIM_BASE_URL  - base URL of the NIM endpoint (e.g. https://integrate.api.nvidia.com/v1)
    NVIDIA_NIM_MODEL     - optional model identifier (default: meta/llama-3.2-90b-vision-instruct)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

try:
    import requests
except ImportError as exc:  # pragma: no cover - runtime failure
    raise SystemExit("The 'requests' package is required to run this script.") from exc


def _load_env(name: str, *, required: bool = True, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"Environment variable '{name}' must be set.")
    if not value:
        return ""
    return value


def _encode_image(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Failed to read image file '{path}': {exc}") from exc
    return base64.b64encode(data).decode("ascii")


def build_payload(image_b64: str, normal_description: str, model: str) -> Dict[str, Any]:
    data_url = f"data:image/jpeg;base64,{image_b64}"
    description = normal_description or "No normal description provided."
    prompt = (
        "You are an inspection classifier. "
        "Decide whether the capture is normal, abnormal, or uncertain. "
        f"Context describing a normal scene:\n{description}"
    )
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Respond with JSON containing fields 'state' (normal|abnormal|uncertain, lower-case), "
                    "'confidence' (0-1 float) and 'reason' (short string or null)."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NIM llama-3.2-90b-vision smoke test")
    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Path to the JPEG/PNG image to classify",
    )
    parser.add_argument(
        "--normal-description",
        default="",
        help="Optional guidance describing a normal capture",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60)",
    )
    args = parser.parse_args(argv)

    api_key = _load_env("NVIDIA_API_KEY")
    base_url = _load_env(
        "NVIDIA_NIM_BASE_URL",
        default="https://integrate.api.nvidia.com/v1",
        required=True,
    ).rstrip("/")
    model = _load_env(
        "NVIDIA_NIM_MODEL",
        default="meta/llama-3.2-90b-vision-instruct",
        required=False,
    )

    if not args.image.exists():
        raise SystemExit(f"Image file '{args.image}' does not exist.")

    image_b64 = _encode_image(args.image)
    payload = build_payload(image_b64, args.normal_description, model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/chat/completions"
    print(f"Requesting {url} model={model} image={args.image}", file=sys.stderr)
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=args.timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(f"NIM request failed: {exc}") from exc

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Unexpected NIM response: {json.dumps(data, indent=2)}") from exc

    print("Raw content:")
    print(content)
    try:
        parsed = json.loads(content)
        print("\nParsed JSON:")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print("\nCould not parse response content as JSON.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
