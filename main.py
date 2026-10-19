"""CLI adapter. Example: python main.py"""

from __future__ import annotations

import argparse
import sys

from app.logging_config import configure_logging
from app.orchestrator import Orchestrator
from app.schemas import DEFAULT_QUERY


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the zoo mammal orchestrator.")
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Two-part question separated by 'Then'. Defaults to the zoo scenario.",
    )
    args = parser.parse_args(argv)
    configure_logging()
    envelope = Orchestrator().run(args.query)
    print(envelope.message)
    return 0 if envelope.status in {"ok", "partial"} else 1


if __name__ == "__main__":
    sys.exit(main())
