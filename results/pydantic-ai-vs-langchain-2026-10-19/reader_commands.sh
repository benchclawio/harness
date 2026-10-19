#!/bin/bash
# The four commands printed in the article, run exactly as shown. Output pasted into the article is the output of this script.
set -e
echo '$ command 1'
curl -s https://pypi.org/pypi/pydantic-ai-slim/2.57.0/json | python3 -c "import sys,json; i=json.load(sys.stdin)['info']; print(i['version']); print([r for r in i['requires_dist'] if 'extra' not in r])"
echo '$ command 2'
curl -s https://pypi.org/pypi/langchain/1.4.6/json | python3 -c "import sys,json; i=json.load(sys.stdin)['info']; print(i['version']); print([r for r in i['requires_dist'] if 'extra' not in r])"
echo '$ command 3'
python3 -c "import io,json,urllib.request as r,zipfile; w=lambda p,v:[x for x in json.load(r.urlopen(f'https://pypi.org/pypi/{p}/{v}/json'))['urls'] if x['packagetype']=='bdist_wheel'][0]['url']; n=lambda p,v:zipfile.ZipFile(io.BytesIO(r.urlopen(w(p,v)).read())).namelist(); a=n('langchain','1.4.6'); b=n('langchain-classic','1.0.8'); print('langchain 1.4.6 chains files:', sum(x.startswith('langchain/chains/') for x in a)); print('langchain-classic 1.0.8 chains files:', sum(x.startswith('langchain_classic/chains/') for x in b))"
echo '$ command 4'
python3 -c "import io,json,urllib.request as r,zipfile; u=[x for x in json.load(r.urlopen('https://pypi.org/pypi/pydantic-ai-slim/2.57.0/json'))['urls'] if x['packagetype']=='bdist_wheel'][0]['url']; z=zipfile.ZipFile(io.BytesIO(r.urlopen(u).read())); print([x for x in z.namelist() if x.endswith('ext/langchain.py')]); print(z.read('pydantic_ai/ext/langchain.py').decode().split(chr(10))[0:12])"
