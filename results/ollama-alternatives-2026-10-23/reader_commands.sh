#!/bin/bash
# The six commands in the article's "check it yourself" section, run in order. Output is pasted into the article.
echo '### 1'; curl -s -H 'Accept: text/markdown' https://docs.ollama.com/context-length | grep 'GiB VRAM'
echo '### 2'; curl -s https://raw.githubusercontent.com/ollama/ollama/HEAD/llama/README.md | grep -m1 'LLAMA_CPP_VERSION'
echo '### 3'; curl -sL https://api.github.com/repos/oobabooga/text-generation-webui | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['full_name'], d['license']['spdx_id'])"
echo '### 4'; curl -s https://api.github.com/repos/nomic-ai/gpt4all/releases/latest | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'], d['published_at'][:10])"
echo '### 5'; curl -s https://raw.githubusercontent.com/AtomicBot-ai/Atomic-Chat/HEAD/LICENSE | grep -i '^Copyright'
echo '### 6'; python3 -c 'import re,html,sys,urllib.request as r; h={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}; t=re.sub(r"<script[\s\S]*?</script>","",r.urlopen(r.Request(sys.argv[1],headers=h)).read().decode()); t=html.unescape(re.sub(r"<[^>]+>"," ",t)); t=re.sub(r"\s+"," ",t); print(*dict.fromkeys(m.group(0).strip() for p in sys.argv[2:] for m in re.finditer(p,t)),sep="\n")' https://lmstudio.ai/app-terms "solely for Your personal and / or internal business purposes" "Version: [A-Z][a-z]+ [0-9]+, [0-9]{4}"
