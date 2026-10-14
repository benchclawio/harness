#!/bin/bash
# Run the checker with a GitHub token read from the local gh credential store (never printed).
export GH_CONFIG_DIR=$HOME/.openclaw/credentials/github-cli
export GITHUB_TOKEN="$($HOME/.openclaw/workspace/tools/github-cli/bin/gh auth token 2>/dev/null)"
cd "$(dirname "$0")" || exit 1
python3 check_cursor_alternatives.py "$@"
