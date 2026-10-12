#!/bin/bash
# Commit the evidence directory, run the secret audits, push, and print the commit. Stops on the first failure.
set -e
cd "$HOME/.openclaw/workspace/projects/benchclaw-harness-repo"
git add results/ai-agent-memory-2026-10-12
git status --short | head
git commit -q -m "Add AI agent memory libraries public-record read, 2026-10-12" -- results/ai-agent-memory-2026-10-12
git log -1 --format='%h %s'
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" post-commit
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" pre-push
git push -q origin HEAD
git log -1 --format='pushed %h'
