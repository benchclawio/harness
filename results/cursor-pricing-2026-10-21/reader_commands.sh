#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
curl -s https://cursor.com/docs/models-and-pricing.md | grep -E '^\| \*\*(Free|Plus|Premium|Super|Ultra)\*\*' | sed 's/  */ /g' | cut -c1-60
echo '$ command 2'
curl -s https://cursor.com/docs/account/pricing/legacy-cursor-plans.md | grep -E '^\| \*\*(Pro|Pro\+|Ultra|Teams Standard|Teams Premium)\*\*' | sed 's/  */ /g' | cut -c1-70
echo '$ command 3'
curl -s https://cursor.com/docs/models-and-pricing.md | grep -o 'Cursor Token Rate of \$0.25 per million tokens' | head -1
echo '$ command 4'
python3 -c "t=1200+5300+940000+50000; b=1.2e3*2/1e6+5.3e3*10/1e6+940e3*0.10/1e6+50e3*2.5/1e6; e=0.25*t/1e6; print(round(b,4), round(e,4), round(e/b*100,1))"
