#!/bin/bash
# Read-only: first lines of the licence files for the three projects whose GitHub licence field is odd.
for r in vercel/ai mastra-ai/mastra microsoft/autogen; do
  echo "== $r"
  for f in LICENSE LICENSE.md LICENSE-CODE; do
    curl -s "https://raw.githubusercontent.com/$r/HEAD/$f" | head -4 | cut -c1-160 | sed "s/^/  $f: /"
  done
done
curl -s https://raw.githubusercontent.com/mastra-ai/mastra/HEAD/README.md | tr '\n' ' ' | grep -o -i -E ".{0,100}(Elastic|Apache|license).{0,140}" | head -3
