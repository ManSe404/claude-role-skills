#!/usr/bin/env python3
"""Copy the shared files into every skill that uses them, or check that the copies match.

Usage: python3 tools/sync_shared.py          # write the copies
       python3 tools/sync_shared.py --check  # exit 1 if a copy is missing or differs

A skill must be self-contained (an installed plugin only has its own folder), so each skill that
draws a page carries its own copy of the renderer, the page format and the fonts. shared/ is the single
source; a skill takes the copies when its SKILL.md mentions render_page.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = {
    "shared/render_page.py": "scripts/render_page.py",
    "shared/page-format.md": "references/page-format.md",
    **{f"shared/fonts/{f.name}": f"assets/fonts/{f.name}" for f in sorted((ROOT / "shared" / "fonts").iterdir())},
}


def skills() -> list[Path]:
    return sorted(
        p.parent for p in ROOT.glob("plugins/*/skills/*/SKILL.md") if "render_page.py" in p.read_text("utf-8")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for skill in skills():
        for source, target in SHARED.items():
            content = (ROOT / source).read_bytes()
            dest = skill / target
            if dest.exists() and dest.read_bytes() == content:
                continue
            if args.check:
                stale.append(dest.relative_to(ROOT).as_posix())
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                print(f"wrote {dest.relative_to(ROOT)}")
    if stale:
        print("out of date, run tools/sync_shared.py:\n  " + "\n  ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
