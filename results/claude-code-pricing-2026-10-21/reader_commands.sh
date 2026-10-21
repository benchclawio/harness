#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
curl -s https://platform.claude.com/docs/en/about-claude/pricing.md | grep -E '^\| Claude (Sonnet 5.5|Opus 5.5|Fable 5.1) ' | sed 's/  */ /g' | head -3
echo '$ command 2'
curl -s https://code.claude.com/docs/en/costs.md | grep -o 'per developer per active day[^,]*' | head -1
echo '$ command 3'
python3 -c "print(round(1.2e3*3/1e6 + 5.3e3*15/1e6 + 940e3*0.30/1e6 + 50e3*3.75/1e6, 2))"
echo '$ command 4'
curl -s https://claude.com/pricing | grep -o 'data-plan="[a-z_0-9]*"[^>]*>[^<]*' | sort -u
