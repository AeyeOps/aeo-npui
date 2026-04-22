#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read().decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a Chrome CDP HTTP endpoint")
    parser.add_argument("--port", type=int, default=9222, help="CDP port on localhost")
    parser.add_argument(
        "--endpoint",
        choices=("version", "list"),
        default="version",
        help="CDP JSON endpoint to query",
    )
    parser.add_argument("--retries", type=int, default=20, help="Number of polling attempts")
    parser.add_argument("--sleep-seconds", type=float, default=0.5, help="Delay between attempts")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}/json/{args.endpoint}"
    last_error = None
    for _ in range(args.retries):
        try:
            payload = fetch(url)
            try:
                print(json.dumps(json.loads(payload), indent=2))
            except json.JSONDecodeError:
                print(payload)
            return 0
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(args.sleep_seconds)

    raise SystemExit(f"CDP probe failed for {url}: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
