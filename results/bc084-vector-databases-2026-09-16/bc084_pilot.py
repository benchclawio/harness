"""Non-scored pilot: one repetition per subject, validated. Subject's container
must already be running and reachable before this script is invoked for that subject.
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/root/bc084")
from bc084_harness import run_repetition, validate_repetition
from bc084_adapters import QdrantAdapter, WeaviateAdapter, ChromaAdapter, PineconeAdapter

SUBJECT = sys.argv[1]

corpus_vectors = np.load("/root/bc084/corpus_embeddings.npy")
query_vectors = np.load("/root/bc084/query_embeddings.npy")
corpus_ids = json.load(open("/root/bc084/corpus_ids.json"))
query_ids = json.load(open("/root/bc084/query_ids.json"))

qrels = {}
with open("/root/bc084/corpus/scifact/qrels/test.tsv") as f:
    next(f)
    for line in f:
        qid, cid, score = line.strip().split("\t")
        qrels.setdefault(qid, set()).add(cid)

ADAPTERS = {
    "qdrant": QdrantAdapter,
    "weaviate": WeaviateAdapter,
    "chroma": ChromaAdapter,
    "pinecone": PineconeAdapter,
}

client = ADAPTERS[SUBJECT]()
record = run_repetition(
    client,
    corpus_ids,
    corpus_vectors,
    query_ids,
    query_vectors,
    qrels,
    k=10,
    scored=False,
    rep_index=-1,
)
if hasattr(client, "close"):
    client.close()

valid, reasons = validate_repetition(record, len(corpus_ids), len(query_ids))

summary = {
    "subject": SUBJECT,
    "valid": valid,
    "reasons": reasons,
    "inserted": record["inserted"],
    "insert_failed": record["insert_failed"],
    "index_ready": record["index_ready"],
    "setup_seconds": round(record["setup_seconds"], 2),
    "insert_seconds": round(record["insert_seconds"], 2),
    "index_ready_seconds": round(record["index_ready_seconds"], 2),
    "scored_query_count": record["scored_query_count"],
    "failed_queries": record["failed_queries"],
    "recall_at_10_mean": record["recall_at_10_mean"],
    "ndcg_at_10_mean": record["ndcg_at_10_mean"],
    "precision_at_10_mean": record["precision_at_10_mean"],
    "median_query_latency_ms": round(float(np.median(record["query_latencies_s"])) * 1000, 2),
}
print(json.dumps(summary, indent=2))
with open(f"/root/bc084/pilot-{SUBJECT}.json", "w") as f:
    json.dump(record, f)
