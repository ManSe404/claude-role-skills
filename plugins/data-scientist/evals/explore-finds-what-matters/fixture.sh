#!/usr/bin/env bash
# Builds the acme-churn fixture, with its git history and the sample data, into ./acme-churn.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
builder="$here/../../../../fixtures/build_fixture.py"
[ -f "$builder" ] || { echo "fixture builder not found from $here" >&2; exit 1; }
python3 "$builder" acme-churn "$PWD/acme-churn"
