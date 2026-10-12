#!/bin/bash
# Print published GitHub security advisories for the memory projects that have any (summary lines only).
export GH_CONFIG_DIR=$HOME/.openclaw/credentials/github-cli
T="$($HOME/.openclaw/workspace/tools/github-cli/bin/gh auth token 2>/dev/null)"
for r in topoteretes/cognee getzep/graphiti; do
  echo "== $r"
  curl -s -H "Authorization: Bearer $T" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$r/security-advisories?per_page=20" |
    node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const a of JSON.parse(s)){console.log(a.ghsa_id,a.severity,(a.published_at||"").slice(0,10),a.cve_id||"-","|",a.summary,"| patched:",JSON.stringify((a.vulnerabilities||[]).map(v=>v.patched_versions)))}})'
done
echo "== mem0 + langmem + letta release/commit sanity"
for r in langchain-ai/langmem; do
  curl -s -H "Authorization: Bearer $T" "https://api.github.com/repos/$r/tags?per_page=3" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{console.log(JSON.parse(s).map(t=>t.name).join(", "))})'
done
