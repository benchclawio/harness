# bc-084: Vector Database Benchmark — Pinecone vs Weaviate vs Qdrant vs Chroma

**Question:** On one frozen retrieval corpus, which of Pinecone, Weaviate, Qdrant and Chroma
returns the most relevant top-10 results, and what query-latency tradeoff accompanies that
recall?

**Method:** BEIR SciFact test split (5,183 docs, 300 queries, CC-BY-SA-4.0), embedded once with
`sentence-transformers/all-MiniLM-L6-v2` and reused byte-for-byte by every arm. 20 fresh-index
scored repetitions per subject, interleaved run order, one container active at a time, on a
single throwaway CX23 host. Full details in `run-manifest.json`; full protocol in
`methodology/vector-databases-v0.1.0.md` (repo root) and `operations/bc084-vector-database-run-plan-2026-09-09.md`.

## Result

| Subject | Recall@10 | nDCG@10 | Query latency median/p95 (ms) | Index build median (s) | Failed queries |
|---|---|---|---|---|---|
| Qdrant v1.19.1 | 0.7833 | 0.6451 | 5.7 / 9.1 | 3.5 | 0 / 6000 |
| Weaviate v1.39.5 | 0.7833 | 0.6451 | 3.5 / 5.8 | 3.0 | 0 / 6000 |
| Pinecone Local | 0.7832 | 0.6449 | 12.0 / 23.0 | 9.2 | 1 / 6000 |
| Chroma 1.5.9 | 0.7812 | 0.6429 | 6.8 / 10.6 | 2.6 | 0 / 6000 |

No practical difference in Recall@10 between any subject and the Qdrant baseline (paired 95%
bootstrap CI, 0.02 practical threshold — see `analysis-summary.json`). The differentiation is
in latency and index-build time, not retrieval quality, on this corpus and scale.

## Files

See `run-manifest.json` for the full file index, exact image digests, corpus/embedding hashes,
and cost ledger. Raw per-query results for every one of the 80 scored repetitions are in
`scored-results-raw.jsonl`.

## What this does not prove

One corpus and one scale. No claim about production performance, multi-tenancy, durability,
replication, filtering quality, hybrid-search quality, operational support, or cost at another
data size. Pinecone was tested via Pinecone Local, an official but explicitly non-production
in-memory emulator — these latency numbers describe that emulator, not Pinecone's managed
service.
