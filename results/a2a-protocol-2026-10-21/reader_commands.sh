#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
curl -s https://api.github.com/repos/a2aproject/A2A/releases/latest | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'], d['published_at'][:10])"
echo '$ command 2'
curl -s https://raw.githubusercontent.com/i-am-bee/acp/HEAD/README.md | grep -o "ACP is now part of A2A under the Linux Foundation"
echo '$ command 3'
for p in crewai/1.15.28 agno/3.1.8 strands-agents/1.61.1 google-adk/2.12.0; do curl -s https://pypi.org/pypi/$p/json | python3 -c "import sys,json; i=json.load(sys.stdin)['info']; print(i['name'], i['version'], sorted({r for r in i['requires_dist'] if r.startswith('a2a-sdk') and 'extra == \"a2a\"' in r}))"; done
echo '$ command 4'
curl -s https://a2a-protocol.org/latest/specification/ | python3 -c "import sys,re; t=re.sub(r'<[^>]+>',' ',sys.stdin.read()); print(sorted(set(re.findall(r'\d+\. (?:JSON-RPC|gRPC|HTTP\+JSON/REST) Protocol Binding', t))))"
