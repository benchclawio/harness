#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
curl -s https://platform.claude.com/docs/en/about-claude/pricing.md | grep -E '^\| Claude (Sonnet 5.5|Opus 5.5|Fable 5.1) ' | sed 's/  */ /g' | head -3
echo '$ command 2'
curl -s https://developers.openai.com/api/docs/guides/prompt-caching.md | grep -E '^\| (Cache read charge|Cache write charge|Minimum cacheable prefix) ' | sed 's/  */ /g' | cut -c1-170
echo '$ command 3'
curl -s https://developers.openai.com/api/docs/pricing.md | grep -E '^\| (gpt-6-sol|gpt-5.5 \(<272K context length\)) ' | head -2 | cut -c1-140
echo '$ command 4'
curl -s https://ai.google.dev/gemini-api/docs/pricing.md.txt | grep -m1 'Context caching price' | cut -c1-200
