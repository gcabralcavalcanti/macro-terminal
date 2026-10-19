"""Command line.

    python -m macro_terminal collect [--only prices,filings]   download, check, cache
    python -m macro_terminal brief [--demo]                    AI daily brief (Claude API; recorded answer without a key)
    python -m macro_terminal ask ["question"] [--demo]          preset questions (or one live question)
    python -m macro_terminal newsletter                        weekly edition in Markdown and HTML
    python -m macro_terminal build                             write the static site to site/
    python -m macro_terminal serve                             local server with live questions (127.0.0.1)
    python -m macro_terminal all [--demo]                      collect + brief + ask + newsletter + build
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="macro_terminal")
    ap.add_argument("command", choices=["collect", "brief", "ask", "build", "newsletter", "serve", "all"])
    ap.add_argument("question", nargs="?", help="for ask: one live question instead of the presets")
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
    if args.command == "ask" and args.question:
        import json
        from .ask import ask_live
        print(json.dumps(ask_live(args.question, mode="demo" if args.demo else "auto"), ensure_ascii=False, indent=1))
    elif args.command in ("ask", "all"):
        from .ask import run_presets
        run_presets(mode="demo" if args.demo else "auto")
    if args.command in ("newsletter", "all"):
        from .newsletter import write_newsletter
        print("newsletter:", write_newsletter())
    if args.command in ("build", "all"):
        from .build import build
        print("site:", build())
    if args.command == "serve":
        from .serve import serve
        serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
