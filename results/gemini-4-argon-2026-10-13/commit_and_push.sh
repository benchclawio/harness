#!/bin/bash
# Commit the evidence directory, run the secret audits, push. Stops on the first failure.
set -e
cd "$HOME/.openclaw/workspace/projects/benchclaw-harness-repo"
git add results/gemini-4-argon-2026-10-13
git commit -q -m "Fix Gemini 4 Argon table parser (19 rows, was 17), 2026-10-13" -- results/gemini-4-argon-2026-10-13
git log -1 --format='%h %s'
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" post-commit
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" pre-push
git push -q origin HEAD
git log -1 --format='pushed %h'
