// bc-064 — MCP server supply-chain static audit.
//
// Tests one specific, widely-repeated, never-measured claim:
//   "MCP server packages currently lack digital signatures, preventing users from easily
//    verifying their authenticity or integrity."
//   — Palo Alto Networks, "MCP Security Exposed", 2025-04-22 (ranks #11 for the target term)
//
// Method: read-only queries to the public npm registry. For each package we record whether
// the latest published version carries (a) registry signatures and (b) a provenance
// attestation, plus repository, licence and publisher metadata.
//
// This installs nothing, executes nothing, and connects to no MCP server. It reads package
// metadata that the registry publishes for every package.
//
// Reproduce:  node audit_mcp_supply_chain.mjs
// Output:     mcp-supply-chain-audit-<date>.json  (raw, one record per package)

import fs from "node:fs/promises";
import path from "node:path";

const REGISTRY = "https://registry.npmjs.org";
const SEARCH_TEXT = "mcp server";
const SEARCH_SIZE = 100;
const DELAY_MS = 120; // be polite to the registry
const OUT_DIR = path.dirname(new URL(import.meta.url).pathname);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url) {
  const res = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "benchclaw-audit/1.0 (+https://benchclaw.io)" },
    signal: AbortSignal.timeout(25_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

// npm's fuzzy search returns anything loosely matching. Keep only packages whose NAME
// actually identifies an MCP package — that is the population a developer installs.
function isMcpPackage(name) {
  const n = name.toLowerCase();
  return /(^|[/@\-._])mcp([/\-._]|$)/.test(n) || n.includes("modelcontextprotocol");
}

async function auditPackage(name) {
  const doc = await getJson(`${REGISTRY}/${encodeURIComponent(name).replace("%40", "@")}`);
  const latest = doc["dist-tags"]?.latest;
  if (!latest) return { name, error: "no latest dist-tag" };
  const v = doc.versions?.[latest];
  if (!v) return { name, error: `version ${latest} missing from document` };

  const dist = v.dist ?? {};
  const signatures = Array.isArray(dist.signatures) ? dist.signatures : [];
  const attestations = dist.attestations ?? null;

  let repoUrl = null;
  const repo = v.repository;
  if (typeof repo === "string") repoUrl = repo;
  else if (repo && typeof repo.url === "string") repoUrl = repo.url;

  return {
    name,
    version: latest,
    published_at: doc.time?.[latest] ?? null,
    has_registry_signature: signatures.length > 0,
    signature_keyids: signatures.map((s) => s.keyid),
    has_provenance_attestation: Boolean(attestations),
    provenance_predicate: attestations?.provenance?.predicateType ?? null,
    attestation_url: attestations?.url ?? null,
    repository_url: repoUrl,
    license: v.license ?? null,
    deprecated: Boolean(v.deprecated),
    integrity_algorithm: typeof dist.integrity === "string" ? dist.integrity.split("-")[0] : null,
  };
}

const search = await getJson(
  `${REGISTRY}/-/v1/search?text=${encodeURIComponent(SEARCH_TEXT)}&size=${SEARCH_SIZE}`,
);

const names = search.objects
  .map((o) => o.package.name)
  .filter((n, i, a) => a.indexOf(n) === i)
  .filter(isMcpPackage);

const records = [];
for (const name of names) {
  try {
    records.push(await auditPackage(name));
  } catch (error) {
    records.push({ name, error: String(error.message ?? error) });
  }
  await sleep(DELAY_MS);
}

const ok = records.filter((r) => !r.error);
const signed = ok.filter((r) => r.has_registry_signature);
const attested = ok.filter((r) => r.has_provenance_attestation);

const report = {
  generated_at: new Date().toISOString(),
  method:
    "Read-only public npm registry metadata. No package installed, executed, or connected to. " +
    "Sample = npm search 'mcp server', top 100 by registry relevance, filtered to names that " +
    "identify an MCP package.",
  registry: REGISTRY,
  search_text: SEARCH_TEXT,
  search_size: SEARCH_SIZE,
  search_total_matches: search.total,
  candidates_returned: search.objects.length,
  packages_audited: records.length,
  packages_resolved: ok.length,
  errors: records.length - ok.length,
  totals: {
    with_registry_signature: signed.length,
    with_provenance_attestation: attested.length,
    pct_signed: ok.length ? Number(((signed.length / ok.length) * 100).toFixed(1)) : null,
    pct_attested: ok.length ? Number(((attested.length / ok.length) * 100).toFixed(1)) : null,
  },
  packages: records.sort((a, b) => a.name.localeCompare(b.name)),
};

const date = report.generated_at.slice(0, 10);
const outPath = path.join(OUT_DIR, `mcp-supply-chain-audit-${date}.json`);
await fs.writeFile(outPath, `${JSON.stringify(report, null, 2)}\n`);

console.log(
  JSON.stringify(
    {
      audited: report.packages_audited,
      resolved: report.packages_resolved,
      errors: report.errors,
      ...report.totals,
      out: outPath,
    },
    null,
    2,
  ),
);
