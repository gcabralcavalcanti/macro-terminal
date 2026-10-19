"""Build the terminal and open it. Works offline and without an API key (committed data, recorded AI answers).

python demo.py              # build from data/cache and open output/site/index.html
python demo.py --refresh    # download fresh public data first; AI answers still replayed
python demo.py --refresh --live   # also call the Claude API (needs ANTHROPIC_API_KEY)
"""

import argparse
import webbrowser

from macro_terminal import cache
from macro_terminal.build import build


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="download fresh data (network)")
    ap.add_argument("--live", action="store_true", help="call the Claude API for the brief and the preset questions")
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = ap.parse_args()

    if args.refresh:
        from macro_terminal.ask import run_presets
        from macro_terminal.brief import run_brief
        from macro_terminal.collect import collect
        from macro_terminal.newsletter import write_newsletter

        collect()
        mode = "auto" if args.live else "demo"
        run_brief(mode=mode)
        run_presets(mode=mode)
        write_newsletter()

    page = build()
    for name, s in cache.read_status().items():
        print(f"{name:13} {s['status']:7} last obs {s.get('last_date')}  {len(s.get('issues', []))} warnings")
    print(f"\nopen {page}")
    if not args.no_open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
