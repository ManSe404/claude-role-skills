#!/usr/bin/env bash
# Builds the acme-index fixture, with its git history, into ./acme-index.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-index "$PWD/acme-index"
