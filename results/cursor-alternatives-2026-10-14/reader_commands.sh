#!/bin/bash
# The commands printed in the article's "check it yourself" section, run exactly as shown.
curl -s https://cursor.com/blog/joining-spacex | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' ' | grep -o "Cursor has officially been acquired by [A-Za-z]*" | head -1
curl -s https://raw.githubusercontent.com/continuedev/continue/HEAD/README.md | grep -o "no longer actively maintained and is read-only for all users"
curl -s https://raw.githubusercontent.com/voideditor/void/HEAD/README.md | grep -o "Void is deprecated and no longer accepting contributions"
