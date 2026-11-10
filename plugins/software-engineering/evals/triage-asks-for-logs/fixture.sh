#!/usr/bin/env bash
# Builds the acme-orders fixture with its git history, logs and data into ./acme-orders.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-orders "$PWD/acme-orders"
