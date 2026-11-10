#!/usr/bin/env bash
# Builds the acme-pipeline fixture, with its git history, deliveries and run records, into ./acme-pipeline.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-pipeline "$PWD/acme-pipeline"
