#!/bin/bash
# Run the checker twice; prove byte-identical output.
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D" || exit 1
python3 check_prompt_caching.py --as-of 2026-10-21 > prompt-caching-2026-10-21.json 2> run1.err || { echo "run 1 failed"; cat run1.err; exit 1; }
python3 check_prompt_caching.py --as-of 2026-10-21 > /tmp/pcx-run2.json 2> run2.err || { echo "run 2 failed"; cat run2.err; exit 1; }
rm -f run1.err run2.err
sha256sum prompt-caching-2026-10-21.json /tmp/pcx-run2.json
cmp prompt-caching-2026-10-21.json /tmp/pcx-run2.json && echo IDENTICAL
rm -f /tmp/pcx-run2.json
