#!/bin/bash
# Run the checker twice with a GitHub token from the local gh store (never printed); prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
export GH_CONFIG_DIR=$HOME/.openclaw/credentials/github-cli
export GITHUB_TOKEN="$($HOME/.openclaw/workspace/tools/github-cli/bin/gh auth token 2>/dev/null)"
cd "$D" || exit 1
python3 check_a2a_protocol.py --as-of 2026-10-21T19:00:00Z > a2a-protocol-2026-10-21.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_a2a_protocol.py --as-of 2026-10-21T19:00:00Z > /tmp/a2-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum a2a-protocol-2026-10-21.json /tmp/a2-run2.json
cmp a2a-protocol-2026-10-21.json /tmp/a2-run2.json && echo IDENTICAL
rm -f /tmp/a2-run2.json
