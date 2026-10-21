#!/bin/bash
# Run the checker twice; prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D" || exit 1
python3 check_cursor_pricing.py --as-of 2026-10-21 > cursor-pricing-2026-10-21.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_cursor_pricing.py --as-of 2026-10-21 > /tmp/cu-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum cursor-pricing-2026-10-21.json /tmp/cu-run2.json
cmp cursor-pricing-2026-10-21.json /tmp/cu-run2.json && echo IDENTICAL
rm -f /tmp/cu-run2.json
