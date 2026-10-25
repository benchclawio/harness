#!/bin/bash
# Run the checker twice; prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D" || exit 1
python3 check_claude_duet_safety.py --as-of 2026-10-25 > claude-duet-safety-2026-10-25.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_claude_duet_safety.py --as-of 2026-10-25 > /tmp/cds-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum claude-duet-safety-2026-10-25.json /tmp/cds-run2.json
cmp claude-duet-safety-2026-10-25.json /tmp/cds-run2.json && echo IDENTICAL
rm -f /tmp/cds-run2.json
