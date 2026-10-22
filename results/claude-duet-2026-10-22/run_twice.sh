#!/bin/bash
# Run the checker twice; prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D" || exit 1
python3 check_claude_duet.py --as-of 2026-10-22 > claude-duet-2026-10-22.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_claude_duet.py --as-of 2026-10-22 > /tmp/cd-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum claude-duet-2026-10-22.json /tmp/cd-run2.json
cmp claude-duet-2026-10-22.json /tmp/cd-run2.json && echo IDENTICAL
rm -f /tmp/cd-run2.json
