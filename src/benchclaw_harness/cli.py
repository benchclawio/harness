from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_fixture_pilot
from .validation import verify_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchclaw-harness")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the zero-cost fixture pilot")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify", help="verify an existing bundle")
    verify.add_argument("bundle", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        result = run_fixture_pilot(args.config, args.output)
    else:
        result = verify_bundle(args.bundle)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
