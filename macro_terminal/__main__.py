"""Command line.

    python -m macro_terminal collect [--only prices,filings]   download, check, cache
    python -m macro_terminal brief [--demo]                    AI daily brief (Claude API; recorded answer without a key)
    python -m macro_terminal build                             write the static site to site/
    python -m macro_terminal all [--demo]                      collect + brief + build
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="macro_terminal")
    ap.add_argument("command", choices=["collect", "brief", "build", "newsletter", "all"])
    ap.add_argument("--only", help="comma-separated datasets for collect")
    ap.add_argument("--demo", action="store_true", help="never call the API; replay recorded answers")
    args = ap.parse_args(argv)

    if args.command in ("collect", "all"):
        from .collect import collect
        res = collect(only=args.only.split(",") if args.only else None)
        print("collect:", res)
    if args.command in ("brief", "all"):
        from .brief import run_brief
        run_brief(mode="demo" if args.demo else "auto")
    if args.command in ("newsletter", "all"):
        from .newsletter import write_newsletter
        print("newsletter:", write_newsletter())
    if args.command in ("build", "all"):
        from .build import build
        print("site:", build())
    return 0


if __name__ == "__main__":
    sys.exit(main())
