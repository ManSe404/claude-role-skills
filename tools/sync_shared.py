#!/usr/bin/env python3
"""Copy the shared files into every skill that uses them, or check that the copies match.

Usage: python3 tools/sync_shared.py          # write the copies
       python3 tools/sync_shared.py --check  # exit 1 if a copy is missing or differs

A skill must be self-contained (an installed plugin only has its own folder), so each skill that
draws a page carries its own copy of the renderer, the page format and the fonts, and each skill that
inventories an AI codebase its own ai_inventory.py. shared/ is the single source; a skill takes a
copy when its SKILL.md names the file that marks it (a key of SHARED below).
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
    "data_profile.py": {"shared/data_profile.py": "scripts/data_profile.py"},
    "sql_inventory.py": {"shared/sql_inventory.py": "scripts/sql_inventory.py"},
    "measure.py": {"shared/measure.py": "scripts/measure.py"},
    "model_stats.py": {"shared/model_stats.py": "scripts/model_stats.py"},
    "guard.py": {"shared/guard.py": "scripts/guard.py"},
    "audit_scan.py": {"shared/audit_scan.py": "scripts/audit_scan.py"},
    "incident_timeline.py": {"shared/incident_timeline.py": "scripts/incident_timeline.py"},
    "code_graph.py": {"shared/code_graph.py": "scripts/code_graph.py"},
    "containers.py": {"shared/containers.py": "scripts/containers.py"},
    "cloud_inventory.py": {"shared/cloud_inventory.py": "scripts/cloud_inventory.py"},
    "cloud_prices.py": {"shared/cloud_prices.py": "scripts/cloud_prices.py"},
    # Every skill that names references/cloud/ gets all provider files, so adding a provider needs no change here.
    "references/cloud/": {
        f"shared/cloud/{f.name}": f"references/cloud/{f.name}" for f in sorted((ROOT / "shared" / "cloud").iterdir())
    },
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
