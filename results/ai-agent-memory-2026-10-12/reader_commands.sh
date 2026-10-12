#!/bin/bash
# The three commands printed in the article's "check it yourself" section, run exactly as shown.
curl -s https://pypi.org/pypi/letta/json | python3 -c "import sys,json; i=json.load(sys.stdin)['info']; print(i['version'], '|', i['summary'])"
curl -s https://raw.githubusercontent.com/letta-ai/letta/HEAD/README.md | grep -i "retired"
curl -s https://raw.githubusercontent.com/getzep/zep/HEAD/README.md | grep -i "no longer supported"
