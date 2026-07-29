"""`uv run python -m serving` — run the forecast API with uvicorn.

Binds to 127.0.0.1 by default on purpose: this is a local demo of the registry
handoff, not something that should be reachable from the network by accident.
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="serving", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s | %(message)s")

    import uvicorn

    print(f"docs:     http://{args.host}:{args.port}/docs")
    print(f"forecast: http://{args.host}:{args.port}/forecast?max_horizon=6")
    uvicorn.run("serving.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
