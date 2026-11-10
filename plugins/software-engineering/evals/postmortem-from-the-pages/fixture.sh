#!/usr/bin/env bash
# Builds the acme-orders fixture with its git history, logs and data into ./acme-orders.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-orders "$PWD/acme-orders"
mkdir -p "$PWD/pages"
cp "$here/../../skills/incident-triage/references/example.json" "$PWD/pages/incident-triage-2026-10-03.json"
cp "$here/../../skills/bug-hunt/references/example.json" "$PWD/pages/bug-hunt-2026-10-03.json"
