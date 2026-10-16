#!/bin/bash
# The commands printed in the article's "check it yourself" section, run exactly as shown.
curl -s https://raw.githubusercontent.com/langfuse/langfuse/HEAD/LICENSE | head -1
curl -s https://raw.githubusercontent.com/Arize-ai/phoenix/HEAD/LICENSE | head -1
curl -s https://www.helicone.ai/blog/joining-mintlify | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' ' | grep -o "remain live for the foreseeable future in maintenance mode" | head -1
