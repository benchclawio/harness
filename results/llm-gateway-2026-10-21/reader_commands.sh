#!/bin/bash
# The four commands printed in the article's "check it yourself" section, run exactly as shown. Output pasted into the article is this script's output.
set -e
echo '$ command 1'
for r in BerriAI/litellm Portkey-AI/gateway maximhq/bifrost tensorzero/tensorzero theopenco/llmgateway; do curl -s https://api.github.com/repos/$r | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['full_name'], d['license']['spdx_id'], 'archived' if d['archived'] else 'active', d['pushed_at'][:10])"; done
echo '$ command 2'
curl -s https://raw.githubusercontent.com/BerriAI/litellm/HEAD/LICENSE | head -4
echo '$ command 3'
curl -s https://api.github.com/repos/Portkey-AI/gateway/releases/latest | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'], d['published_at'][:10])"
echo '$ command 4'
curl -s https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents | grep -o 'closed the acquisition of Portkey' | head -1
