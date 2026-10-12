#!/bin/bash
# Run the checker twice, save the first output, and prove the runs agree byte for byte.
D="$(cd "$(dirname "$0")" && pwd)"
bash "$D/run_with_token.sh" --as-of 2026-10-12T19:00:00Z > "$D/agent-memory-2026-10-12.json" 2> "$D/run1.err" || { echo "run 1 failed"; cat "$D/run1.err"; exit 1; }
bash "$D/run_with_token.sh" --as-of 2026-10-12T19:00:00Z > /tmp/agent-memory-run2.json 2> "$D/run2.err" || { echo "run 2 failed"; cat "$D/run2.err"; exit 1; }
rm -f "$D/run1.err" "$D/run2.err"
sha256sum "$D/agent-memory-2026-10-12.json" /tmp/agent-memory-run2.json
cmp "$D/agent-memory-2026-10-12.json" /tmp/agent-memory-run2.json && echo IDENTICAL
rm -f /tmp/agent-memory-run2.json
