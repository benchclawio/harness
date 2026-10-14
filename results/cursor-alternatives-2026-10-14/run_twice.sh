#!/bin/bash
# Run the checker twice, save the first output, and prove the runs agree byte for byte.
D="$(cd "$(dirname "$0")" && pwd)"
bash "$D/run_with_token.sh" --as-of 2026-10-14T17:30:00Z > "$D/cursor-alternatives-2026-10-14.json" 2> "$D/run1.err" || { echo "run 1 failed"; cat "$D/run1.err"; exit 1; }
bash "$D/run_with_token.sh" --as-of 2026-10-14T17:30:00Z > /tmp/cursor-run2.json 2> "$D/run2.err" || { echo "run 2 failed"; cat "$D/run2.err"; exit 1; }
rm -f "$D/run1.err" "$D/run2.err"
sha256sum "$D/cursor-alternatives-2026-10-14.json" /tmp/cursor-run2.json
cmp "$D/cursor-alternatives-2026-10-14.json" /tmp/cursor-run2.json && echo IDENTICAL
rm -f /tmp/cursor-run2.json
