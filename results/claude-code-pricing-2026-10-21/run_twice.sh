#!/bin/bash
# Run the checker twice; prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D" || exit 1
python3 check_claude_code_pricing.py --as-of 2026-10-21 > claude-code-pricing-2026-10-21.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_claude_code_pricing.py --as-of 2026-10-21 > /tmp/cc-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum claude-code-pricing-2026-10-21.json /tmp/cc-run2.json
cmp claude-code-pricing-2026-10-21.json /tmp/cc-run2.json && echo IDENTICAL
rm -f /tmp/cc-run2.json
