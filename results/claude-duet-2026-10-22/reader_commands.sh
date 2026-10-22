#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
python3 -c 'import re,html,sys,urllib.request as r; t=html.unescape(re.sub(r"<[^>]+>"," ",r.urlopen(r.Request(sys.argv[1],headers={"User-Agent":"Mozilla/5.0"})).read().decode())); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://support.claude.com/en/articles/17631495-get-started-with-claude-duet "Pricing\. During[^.]*\." "This limit reset is available until[^.]*\."
echo '$ command 2'
python3 -c 'import re,html,sys,urllib.request as r; t=html.unescape(re.sub(r"<[^>]+>"," ",r.urlopen(r.Request(sys.argv[1],headers={"User-Agent":"Mozilla/5.0"})).read().decode())); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://support.claude.com/en/articles/17631495-get-started-with-claude-duet "You can.t choose a model\. Claude Duet runs on Claude Opus 5\.5" "You can.t watch Claude Duet[^.]*\."
echo '$ command 3'
python3 -c 'import re,html,sys,urllib.request as r; t=html.unescape(re.sub(r"<[^>]+>"," ",r.urlopen(r.Request(sys.argv[1],headers={"User-Agent":"Mozilla/5.0"})).read().decode())); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://learn.chatgpt.com/docs/dots "Pro 100, Pro 200, and Pro 500[^.]*\." "open its computer and select Take over"
echo '$ command 4'
python3 -c 'import re,html,sys,urllib.request as r; t=html.unescape(re.sub(r"<[^>]+>"," ",r.urlopen(r.Request(sys.argv[1],headers={"User-Agent":"Mozilla/5.0"})).read().decode())); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://claude.com/resources/articles/claude-duet "This new classifier and prompt are designed to reject[^.]*\."
