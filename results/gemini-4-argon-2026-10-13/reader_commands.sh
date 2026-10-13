#!/bin/bash
# The commands printed in the article's "check it yourself" section, run exactly as shown.
curl -sL -A "Mozilla/5.0" https://ai.google.dev/gemini-api/docs/pricing | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' ' | grep -o 'Input price Not available \$[0-9.]* through November 30, 2026. \$[0-9.]* starting December 1, 2026' | head -2
curl -s https://deepmind.google/models/model-cards/gemini-4-argon/ | grep -o "knowledge cutoff for Gemini 4 is [A-Za-z]* [0-9]*"
