#!/usr/bin/env python3
"""Read Pinecone's published pricing and cost documentation, print one JSON document.

Standard library only, no API key, no account, nothing is billed. Reads:
  - https://www.pinecone.io/pricing/                          (rates and plan limits)
  - https://docs.pinecone.io/guides/manage-cost/understanding-cost.md   (billing formulas)
  - https://docs.pinecone.io/release-notes/2026.md            (dated pricing changes)
  - https://www.withorb.com/blog/pinecone-pricing             (one third-party explainer)
  - google-ai-overview-pinecone-pricing-2026-10-09.md         (Google's AI Overview, saved next to this script)

Before computing anything of our own it recomputes every worked example Pinecone publishes in
its cost documentation (storage size, query read units, fetch read units, upsert/delete/update
write units). It exits non-zero if a dense or sparse storage, query, fetch, upsert or delete example differs.
Update-table and hybrid-storage rows that differ are reported as data, not as a failure,
because a published example that disagrees with the published formula is itself a finding.

Usage: python3 check_pinecone_pricing.py > out.json
"""
import json
import math
import os
import re
import sys
import urllib.request
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
HERE = os.path.dirname(os.path.abspath(__file__))


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def text_lines(html_text):
    import html as h
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", html_text)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = h.unescape(t)
    return [l.strip() for l in t.splitlines() if l.strip()]


pricing_html = get("https://www.pinecone.io/pricing/")
cost_md = get("https://docs.pinecone.io/guides/manage-cost/understanding-cost.md")
changelog = get("https://docs.pinecone.io/release-notes/2026.md")
orb_html = get("https://www.withorb.com/blog/pinecone-pricing")
aio = open(os.path.join(HERE, "google-ai-overview-pinecone-pricing-2026-10-09.md"), encoding="utf-8").read()

# ---- 1. Pricing page: dimensions table -------------------------------------------------
lines = text_lines(pricing_html)
start = lines.index("Pricing Dimensions")
block = lines[start:]
LABELS = ["Database", "Storage", "Write Units", "Read Units", "Egress", "Import from object storage",
          "Backups", "Restore from backup", "Cross-region restore", "Assistant", "Document Limit",
          "Input Tokens", "Output Tokens", "Context Processed Tokens", "Evaluation Processed Tokens",
          "Evaluation Output Tokens", "Ingestion Units", "Region", "Inference - Embedding",
          "Inference - Reranking", "Org Management"]


def section(first, last):
    """Lines after the first occurrence of `first` (in block) up to the next label."""
    i = block.index(first)
    j = i + 1
    while j < len(block) and block[j] not in LABELS:
        j += 1
    return block[i + 1:j]


def groups(vals):
    out, cur = [], None
    for v in vals:
        if v.startswith("Up to") or v == "Unlimited":
            cur = [v]
            out.append(cur)
        elif cur is not None:
            cur.append(v)
    return out


PLANS = ["Starter", "Builder", "Standard", "Enterprise"]


def by_plan(vals):
    g = groups(vals)
    return dict(zip(PLANS, [" ".join(x) for x in g])) if len(g) == 4 else {"raw": vals}


db_end = block.index("Assistant")
db_block = block[:db_end]


def db_section(label):
    i = db_block.index(label)
    j = i + 1
    while j < len(db_block) and db_block[j] not in LABELS:
        j += 1
    return db_block[i + 1:j]


def asst_section(label):
    k = block.index("Assistant")
    sub = block[k:]
    i = sub.index(label)
    j = i + 1
    while j < len(sub) and sub[j] not in LABELS:
        j += 1
    return sub[i + 1:j]


database = {
    "storage": by_plan(db_section("Storage")),
    "write_units": by_plan(db_section("Write Units")),
    "read_units": by_plan(db_section("Read Units")),
    "egress": by_plan(db_section("Egress")),
    "import_from_object_storage": db_section("Import from object storage"),
    "backups": db_section("Backups"),
    "restore_from_backup": db_section("Restore from backup"),
}
assistant = {
    "storage": asst_section("Storage"),
    "input_tokens": asst_section("Input Tokens"),
    "output_tokens": asst_section("Output Tokens"),
}
embedding = {
    "llama-text-embed-v2": block[block.index("llama-text-embed-v2") + 1:block.index("multilingual-e5-large")],
    "multilingual-e5-large": block[block.index("multilingual-e5-large") + 1:block.index("pinecone-sparse-english-v0")],
}

page_text = "\n".join(lines)


def has(s, hay=page_text):
    return s in hay


plan_prices = {
    "Builder": "$20/month flat" if has("$20/month flat") else None,
    "Standard": "$50/month min. usage" if has("$50/month") and has("min. usage") else None,
    "Enterprise": "$500/month min. usage" if has("$500/month") and has("min. usage") else None,
    "Standard_trial": "3 week trial includes $300 credits" if has("3 week trial includes $300 credits") else None,
    "HIPAA_add_on_standard": "$190/mo" if has("$190/mo") else None,
}


def money_range(s):
    m = re.search(r"\$([0-9.]+)-\$([0-9.]+) per million", s)
    return (Decimal(m.group(1)), Decimal(m.group(2))) if m else None


write_rate = {"Standard": money_range(database["write_units"]["Standard"]),
              "Enterprise": money_range(database["write_units"]["Enterprise"])}
read_rate = {"Standard": money_range(database["read_units"]["Standard"]),
             "Enterprise": money_range(database["read_units"]["Enterprise"])}
STORAGE_RATE = Decimal(re.search(r"\$([0-9.]+)/GB/mo", database["storage"]["Standard"]).group(1))
EGRESS_RATE = Decimal(re.search(r"\$([0-9.]+)/GB", database["egress"]["Standard"]).group(1))
IMPORT_RATE = Decimal(re.search(r"\$([0-9.]+) per GB", " ".join(database["import_from_object_storage"])).group(1))

# ---- 2. Docs: recompute every published example ----------------------------------------
D = Decimal


def size_gb(records, dims, meta, ident=8, sparse=0):
    return D(records) * (D(ident) + D(meta) + D(dims) * 4 + D(sparse) * 8) / D(10 ** 9)


def r2(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def wu(n, record_bytes):
    kb = r2(D(record_bytes) / D(1000))
    return max(5, int((D(n) * kb).to_integral_value(rounding=ROUND_CEILING)))


def rows(header_regex):
    """Markdown table rows after the first table whose header matches header_regex."""
    m = re.search(header_regex, cost_md)
    if not m:
        return []
    out = []
    for ln in cost_md[m.end():].splitlines()[1:]:
        ln = ln.strip()
        if not ln.startswith("|"):
            if out:
                break
            continue
        if re.match(r"^\|\s*:?-", ln):
            continue
        out.append([c.strip() for c in ln.strip("|").split("|")])
    return out


def num(s):
    return D(re.sub(r"[^0-9.]", "", s))


checks = {"storage_dense": [], "storage_sparse": [], "storage_hybrid": [], "query_ru": [], "fetch_ru": [],
          "upsert_wu": [], "delete_wu": [], "update_wu": []}

for rec, dims, meta, pub in rows(r"\| Records \| Dense vector dimensions \| Avg metadata size \| Index size \|"):
    c = size_gb(num(rec), num(dims), num(meta))
    checks["storage_dense"].append({"records": int(num(rec)), "dims": int(num(dims)), "metadata_bytes": int(num(meta)),
                                    "published_gb": float(num(pub)), "computed_gb": float(r2(c) if c < 10 else c.quantize(D("0.1"), rounding=ROUND_HALF_UP))})
for rec, nz, meta, pub in rows(r"\| Records \| Avg number of non-zero sparse values \| Avg metadata size \| Index size \|"):
    c = size_gb(num(rec), 0, num(meta), sparse=num(nz))
    checks["storage_sparse"].append({"records": int(num(rec)), "sparse_values": int(num(nz)), "metadata_bytes": int(num(meta)),
                                     "published_gb": float(num(pub)), "computed_gb": float(r2(c) if c < 10 else c.quantize(D("0.1"), rounding=ROUND_HALF_UP))})
for rec, dims, nz, meta, pub in rows(r"\| Records \| Dense vector dimensions \| Avg number of non-zero sparse values \| Avg metadata size \| Index size \|"):
    c = size_gb(num(rec), num(dims), num(meta), sparse=num(nz))
    checks["storage_hybrid"].append({"records": int(num(rec)), "dims": int(num(dims)), "sparse_values": int(num(nz)),
                                     "metadata_bytes": int(num(meta)), "published_gb": float(num(pub)),
                                     "computed_gb": float(r2(c) if c < 10 else c.quantize(D("0.1"), rounding=ROUND_HALF_UP))})

for ns, pub in rows(r"\| Namespace size \| Read units per query \|"):
    gb = D("0.25") if ns.startswith("\\<") or ns.startswith("<") else num(ns)
    checks["query_ru"].append({"namespace": ns.replace("\\", ""), "published_ru": float(num(pub)),
                               "computed_ru": float(max(D("0.25"), gb))})
for n, pub in rows(r"\| Fetched records \| RUs \|"):
    comp = max(1, int((num(n) / 10).to_integral_value(rounding=ROUND_CEILING)))
    checks["fetch_ru"].append({"records": int(num(n)), "published_ru": int(num(pub)), "computed_ru": comp})

upsert_rows = rows(r"\| Records per batch \| Dimension \| Avg\. metadata size \| Avg\. record size \| WUs \|")
for n, dims, meta, size, pub in upsert_rows:
    comp = wu(num(n), num(dims) * 4 + num(meta))
    checks["upsert_wu"].append({"records": int(num(n)), "dims": int(num(dims)), "metadata_bytes": int(num(meta)),
                                "published_wu": int(num(pub)), "computed_wu": comp})
# the delete table is the same layout; find the second occurrence
second = [m.end() for m in re.finditer(r"\| Records per batch \| Dimension \| Avg\. metadata size \| Avg\. record size \| WUs \|", cost_md)]
if len(second) > 1:
    out = []
    for ln in cost_md[second[1]:].splitlines()[1:]:
        ln = ln.strip()
        if not ln.startswith("|"):
            if out:
                break
            continue
        if re.match(r"^\|\s*:?-", ln):
            continue
        out.append([c.strip() for c in ln.strip("|").split("|")])
    for n, dims, meta, size, pub in out:
        comp = wu(num(n), num(dims) * 4 + num(meta))
        checks["delete_wu"].append({"records": int(num(n)), "dims": int(num(dims)), "metadata_bytes": int(num(meta)),
                                    "published_wu": int(num(pub)), "computed_wu": comp})

for new, prev, pub in rows(r"\| New record size \| Previous record size \| WUs \|"):
    comp = max(5, int(((num(new) + num(prev))).to_integral_value(rounding=ROUND_CEILING)))
    checks["update_wu"].append({"new_kb": float(num(new)), "previous_kb": float(num(prev)),
                                "published_wu": int(num(pub)), "computed_wu": comp})


def mismatches(key, pub, comp):
    return [r for r in checks[key] if r[pub] != r[comp]]


strict = {"storage_dense": ("published_gb", "computed_gb"), "storage_sparse": ("published_gb", "computed_gb"),
          "query_ru": ("published_ru", "computed_ru"),
          "fetch_ru": ("published_ru", "computed_ru"), "upsert_wu": ("published_wu", "computed_wu"),
          "delete_wu": ("published_wu", "computed_wu")}
selfcheck = {k: {"rows": len(checks[k]), "mismatches": mismatches(k, *strict[k])} for k in strict}
# Reported as data, not a failure: published examples that disagree with the published formula.
selfcheck["storage_hybrid"] = {"rows": len(checks["storage_hybrid"]), "mismatches": mismatches("storage_hybrid", "published_gb", "computed_gb")}
selfcheck["update_wu"] = {"rows": len(checks["update_wu"]), "mismatches": mismatches("update_wu", "published_wu", "computed_wu")}
selfcheck["strict_ok"] = all(len(selfcheck[k]["mismatches"]) == 0 and selfcheck[k]["rows"] > 0 for k in strict)
if not selfcheck["strict_ok"]:
    json.dump({"selfcheck": selfcheck}, sys.stdout, indent=2, sort_keys=True)
    sys.exit(1)

# ---- 3. Our arithmetic (published rates only; Standard plan, low and high ends) ---------
LOW, HIGH = 0, 1


def usd(x):
    return float(D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP))


def workload(name, records, dims, meta, ns_gb, queries, upserts, batch):
    store_gb = size_gb(records, dims, meta)
    ru = D(queries) * max(D("0.25"), D(ns_gb))
    per_upsert_batch = wu(batch, D(dims) * 4 + D(meta))
    wus = D(upserts) / D(batch) * D(per_upsert_batch)
    out = {"name": name, "records": records, "dims": dims, "metadata_bytes": meta,
           "index_gb": float(store_gb), "namespace_gb": float(ns_gb), "queries_per_month": queries,
           "ru_per_query": float(max(D("0.25"), D(ns_gb))), "read_units_per_month": float(ru),
           "upserted_records_per_month": upserts, "wu_per_upsert_batch": per_upsert_batch,
           "write_units_per_month": float(wus)}
    for end, tag in ((LOW, "low"), (HIGH, "high")):
        storage = store_gb * STORAGE_RATE
        reads = ru / D(10 ** 6) * read_rate["Standard"][end]
        writes = wus / D(10 ** 6) * write_rate["Standard"][end]
        usage = storage + reads + writes
        out[tag] = {"storage_usd": usd(storage), "reads_usd": usd(reads), "writes_usd": usd(writes),
                    "usage_usd": usd(usage), "standard_bill_usd": usd(max(usage, D(50)))}
    return out


w_big = workload("one 7.15 GB namespace", 1_000_000, 1536, 1000, size_gb(1_000_000, 1536, 1000), 1_000_000, 100_000, 100)
w_tenant = workload("same data, 1,000 tenant namespaces", 1_000_000, 1536, 1000, size_gb(1_000, 1536, 1000), 1_000_000, 100_000, 100)

one_off = {
    "initial_load_by_upsert_write_units": float(D(1_000_000) / D(100) * wu(100, 1536 * 4 + 1000)),
    "initial_load_by_upsert_usd_low_high": [usd(D(1_000_000) / D(100) * wu(100, 1536 * 4 + 1000) / D(10 ** 6) * write_rate["Standard"][i]) for i in (0, 1)],
    "initial_load_by_import_usd": usd(size_gb(1_000_000, 1536, 1000) * IMPORT_RATE),
}

# Queries per month at which read units alone reach the $50 Standard minimum.
breakeven = []
for gb in (D("0.25"), D("1"), size_gb(1_000_000, 1536, 1000)):
    ru_per = max(D("0.25"), gb)
    breakeven.append({"namespace_gb": float(gb), "ru_per_query": float(ru_per),
                      "queries_to_reach_50_usd_high_rate": int(D(50) / read_rate["Standard"][HIGH] * D(10 ** 6) / ru_per),
                      "queries_to_reach_50_usd_low_rate": int(D(50) / read_rate["Standard"][LOW] * D(10 ** 6) / ru_per)})

# What the free and flat plans hold, for a 100,000-record, 1536-dimension, 500-byte-metadata index.
rec_bytes = 8 + 500 + 1536 * 4
small_gb = size_gb(100_000, 1536, 500)
caps = {"Starter": {"storage_gb": 2, "ru": 1_000_000, "wu": 2_000_000, "egress_gb": 1},
        "Builder": {"storage_gb": 10, "ru": 2_000_000, "wu": 5_000_000, "egress_gb": 10}}
small = {"index_gb": float(small_gb), "record_bytes": rec_bytes, "plans": {}}
for p, c in caps.items():
    small["plans"][p] = {"max_records_by_storage": int(D(c["storage_gb"]) * D(10 ** 9) / D(rec_bytes)),
                         "max_queries_by_read_units": int(D(c["ru"]) / max(D("0.25"), small_gb)),
                         "max_new_records_by_write_units": int(D(c["wu"]) / r2(D(rec_bytes) / D(1000)))}

# ---- 4. Dated pricing changes in the 2026 changelog -------------------------------------
changes = []
for m in re.finditer(r'<Update label="([0-9-]+)" tags=\{\[([^\]]*)\]\}>\s*### ([^\n]+)', changelog):
    date, tags, head = m.groups()
    if "Billing" in tags or re.search(r"pricing|plan|egress|Builder|import", head, re.I):
        changes.append({"date": date, "tags": tags.replace('"', ""), "heading": head.strip()})

# ---- 5. Third-party and AI Overview claims against the live page -------------------------
orb_lines = text_lines(orb_html)
orb_text = "\n".join(orb_lines)


def orb_has(s):
    return s in orb_text


orb = {
    "says_standard_embedding_0_08_per_million_tokens": orb_has("$0.08 per million tokens"),
    "says_standard_writes_4_per_million": orb_has("$4 per million write units"),
    "says_standard_reads_16_per_million": orb_has("$16 per million read units"),
    "says_pro_support_499_a_month": orb_has("$499 per month"),
    "mentions_builder_plan": "Builder" in orb_text,
    "live_llama_text_embed_v2_lines_starter_builder_standard_enterprise": embedding["llama-text-embed-v2"],
    "live_multilingual_e5_large_lines_starter_builder_standard_enterprise": embedding["multilingual-e5-large"],
    "live_write_units_standard": database["write_units"]["Standard"],
    "live_read_units_standard": database["read_units"]["Standard"],
}
aio_claims = {
    "says_starter_2gb_storage_1gb_per_org": "2 GB storage (1 GB max per organization)" in aio,
    "live_starter_database_storage": database["storage"]["Starter"],
    "live_assistant_storage_lines_starter_builder_standard_enterprise": assistant["storage"],
    "says_builder_free_storage_3gb": "free storage up to 3 GB per organization" in aio,
    "live_builder_database_storage": database["storage"]["Builder"],
    "says_standard_storage_3_per_gb_or_0_33": "Storage costs $3/GB per month (or ~$0.33/GB" in aio,
    "live_standard_database_storage": database["storage"]["Standard"],
}

result = {
    "sources": ["https://www.pinecone.io/pricing/", "https://docs.pinecone.io/guides/manage-cost/understanding-cost.md",
                "https://docs.pinecone.io/release-notes/2026.md", "https://www.withorb.com/blog/pinecone-pricing"],
    "plan_prices": plan_prices,
    "database_dimensions": database,
    "assistant_dimensions": {k: v for k, v in assistant.items()},
    "embedding_dimensions": embedding,
    "rates_standard_usd": {"storage_per_gb_month": float(STORAGE_RATE), "egress_per_gb": float(EGRESS_RATE),
                           "import_per_gb": float(IMPORT_RATE),
                           "write_per_million_low_high": [float(x) for x in write_rate["Standard"]],
                           "read_per_million_low_high": [float(x) for x in read_rate["Standard"]]},
    "rates_enterprise_usd": {"write_per_million_low_high": [float(x) for x in write_rate["Enterprise"]],
                             "read_per_million_low_high": [float(x) for x in read_rate["Enterprise"]]},
    "selfcheck": selfcheck,
    "workloads": [w_big, w_tenant],
    "one_off": one_off,
    "read_unit_breakeven_against_50_usd_minimum": breakeven,
    "small_index_caps": small,
    "changelog_pricing_changes_2026": changes,
    "third_party_orb": orb,
    "ai_overview_vs_live_page": aio_claims,
}
json.dump(result, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
