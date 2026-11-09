#!/usr/bin/env bash
# Builds the acme-assist fixture, with its git history and the stock export, into ./acme-assist.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-assist "$PWD/acme-assist"
