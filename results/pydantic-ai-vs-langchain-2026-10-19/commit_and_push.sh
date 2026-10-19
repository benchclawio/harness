#!/bin/bash
# Commit the evidence directory, run the secret audits, push. Stops on the first failure.
set -e
cd "$HOME/.openclaw/workspace/projects/benchclaw-harness-repo"
git add results/pydantic-ai-vs-langchain-2026-10-19
git commit -q -m "Add Pydantic AI vs LangChain public-record read, 2026-10-19" -- results/pydantic-ai-vs-langchain-2026-10-19
git log -1 --format='%h %s'
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" post-commit
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" pre-push
git push -q origin HEAD
git log -1 --format='pushed %h'
