#!/bin/bash
# The commands printed in the article's "check it yourself" section, run exactly as shown.
curl -s https://pypi.org/pypi/langchain/json | python3 -c "import sys,json; i=json.load(sys.stdin)['info']; print(i['version']); print([r for r in i['requires_dist'] if 'extra' not in r])"
curl -s https://raw.githubusercontent.com/microsoft/autogen/HEAD/README.md | grep -m1 -o "Project archived and no longer maintained"
curl -s https://raw.githubusercontent.com/microsoft/semantic-kernel/HEAD/README.md | grep -m1 -o "successor to Semantic Kernel"
