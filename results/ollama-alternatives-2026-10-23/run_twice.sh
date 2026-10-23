#!/bin/bash
# Run the checker twice with a GitHub token from the local gh store (never printed); prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
export GH_CONFIG_DIR=$HOME/.openclaw/credentials/github-cli
export GITHUB_TOKEN="$($HOME/.openclaw/workspace/tools/github-cli/bin/gh auth token 2>/dev/null)"
cd "$D" || exit 1
python3 check_ollama_alternatives.py --as-of 2026-10-23T14:30:00Z > ollama-alternatives-2026-10-23.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_ollama_alternatives.py --as-of 2026-10-23T14:30:00Z > /tmp/ol-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum ollama-alternatives-2026-10-23.json /tmp/ol-run2.json
cmp ollama-alternatives-2026-10-23.json /tmp/ol-run2.json && echo IDENTICAL
rm -f /tmp/ol-run2.json
