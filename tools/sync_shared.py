#!/usr/bin/env python3
"""Copy the shared files into every skill that uses them, or check that the copies match.

Usage: python3 tools/sync_shared.py          # write the copies
       python3 tools/sync_shared.py --check  # exit 1 if a copy is missing or differs

A skill must be self-contained (an installed plugin only has its own folder), so each skill that
draws a page carries its own copy of the renderer, the page format and the fonts, and each skill that
inventories an AI codebase its own ai_inventory.py. shared/ is the single source; a skill takes a
copy when its SKILL.md names the file that marks it (render_page.py, ai_inventory.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# marker named in SKILL.md -> {shared source: target inside the skill}
SHARED = {
    "render_page.py": {
        "shared/render_page.py": "scripts/render_page.py",
        "shared/page-format.md": "references/page-format.md",
        **{f"shared/fonts/{f.name}": f"assets/fonts/{f.name}" for f in sorted((ROOT / "shared" / "fonts").iterdir())},
    },
    "ai_inventory.py": {"shared/ai_inventory.py": "scripts/ai_inventory.py"},
}


def copies() -> list[tuple[Path, str, str]]:
    """(skill, source, target) for every copy a skill needs."""
    result = []
    for path in sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")):
        text = path.read_text("utf-8")
        for marker, files in SHARED.items():
            if marker in text:
                result += [(path.parent, source, target) for source, target in files.items()]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = []
    for skill, source, target in copies():
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
