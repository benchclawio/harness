#!/bin/bash
# The five commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
curl -s https://raw.githubusercontent.com/Arize-ai/phoenix/HEAD/LICENSE | head -1
echo '$ command 2'
curl -s https://raw.githubusercontent.com/langfuse/langfuse/HEAD/LICENSE | grep -E 'MIT Expat|"ee/"' | cut -c1-120
echo '$ command 3'
curl -s https://raw.githubusercontent.com/promptfoo/promptfoo/HEAD/README.md | grep -o "Promptfoo is now part of OpenAI" | head -1
echo '$ command 4'
python3 -c 'import re,html,sys,urllib.request as r; h={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}; t=re.sub(r"<script[\s\S]*?</script>","",r.urlopen(r.Request(sys.argv[1],headers=h)).read().decode()); t=html.unescape(re.sub(r"<[^>]+>"," ",t)); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://www.braintrust.dev/pricing "Pro For AI native teams [$]249 / month" "Starter For everyone [$]0 / month"
echo '$ command 5'
curl -s "https://api.github.com/orgs/braintrustdata/repos?per_page=100" | python3 -c "import sys,json; [print(r['name'], r['license'] and r['license']['spdx_id']) for r in sorted(json.load(sys.stdin), key=lambda r: r['name']) if r['name'] in ('autoevals','braintrust-sdk-python','helm','terraform-aws-braintrust-data-plane')]"
