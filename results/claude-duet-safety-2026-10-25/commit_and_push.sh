#!/bin/bash
# Commit the evidence directory, run the secret audits, push. Stops on the first failure.
set -e
cd "$HOME/.openclaw/workspace/projects/benchclaw-harness-repo"
git add results/claude-duet-safety-2026-10-25
git commit -q -m "Add claude-duet-safety public-record read, 2026-10-25" -- results/claude-duet-safety-2026-10-25
git log -1 --format='%h %s'
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" post-commit
bash "$HOME/.openclaw/workspace/scripts/run-benchclaw-git-secret-audit.sh" pre-push
git push -q origin HEAD
git log -1 --format='pushed %h'
