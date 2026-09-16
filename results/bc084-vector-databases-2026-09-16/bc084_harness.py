"""Generic vector-database benchmark harness for bc-084.

One generic runner drives every arm through the same DBClient interface.
No subject-specific logic lives outside each adapter's insert/query/wait_ready.
"""
import time
import uuid
from abc import ABC, abstractmethod

import numpy as np


class DBClient(ABC):
    name: str

    @abstractmethod
    def setup(self, dim: int) -> None:
        """Create a fresh, empty index/collection with the given vector dimension."""

    @abstractmethod
    def insert(self, ids: list, vectors: np.ndarray) -> dict:
        """Insert all (id, vector) pairs. Return {'inserted': n, 'failed': n}."""

    @abstractmethod
    def wait_ready(self, expected_count: int, timeout_s: float = 60.0) -> bool:
        """Block until the index reports it holds expected_count records and is queryable."""

    @abstractmethod
    def query(self, vector: np.ndarray, k: int) -> list:
        """Return up to k result ids, ordered most-relevant first."""

    @abstractmethod
    def teardown(self) -> None:
        """Delete the collection/index so the next repetition starts fresh."""


def run_repetition(
    client: DBClient,
    corpus_ids: list,
    corpus_vectors: np.ndarray,
    query_ids: list,
    query_vectors: np.ndarray,
    qrels: dict,
    k: int = 10,
    scored: bool = True,
    rep_index: int = 0,
    warmup_passes: int = 0,
) -> dict:
    dim = corpus_vectors.shape[1]
    record = {
        "subject": client.name,
        "rep_index": rep_index,
        "scored": scored,
        "corpus_count_expected": len(corpus_ids),
        "query_count_expected": len(query_ids),
    }

    t0 = time.time()
    client.setup(dim)
    record["setup_seconds"] = time.time() - t0

    t0 = time.time()
    insert_result = client.insert(corpus_ids, corpus_vectors)
    record["insert_seconds"] = time.time() - t0
    record["inserted"] = insert_result.get("inserted", 0)
    record["insert_failed"] = insert_result.get("failed", 0)

    t0 = time.time()
    ready = client.wait_ready(len(corpus_ids))
    record["index_ready_seconds"] = time.time() - t0
    record["index_ready"] = ready

    for _ in range(warmup_passes):
        for qvec in query_vectors:
            try:
                client.query(qvec, k)
            except Exception:  # noqa: BLE001 - warmup failures are not scored
                pass
    record["warmup_passes"] = warmup_passes

    query_results = []
    query_latencies = []
    failed_queries = 0
    for qid, qvec in zip(query_ids, query_vectors):
        t0 = time.time()
        try:
            result_ids = client.query(qvec, k)
            ok = True
        except Exception as e:  # noqa: BLE001 - benchmark must record, not crash
            result_ids = []
            ok = False
            failed_queries += 1
        latency = time.time() - t0
        query_latencies.append(latency)
        query_results.append(
            {
                "query_id": qid,
                "result_ids": result_ids,
                "result_count": len(result_ids),
                "latency_s": latency,
                "ok": ok,
            }
        )

    record["failed_queries"] = failed_queries
    record["query_latencies_s"] = query_latencies

    recalls = []
    ndcgs = []
    precisions = []
    for qr in query_results:
        qid = qr["query_id"]
        relevant = qrels.get(qid, set())
        if not relevant:
            continue
        retrieved = qr["result_ids"][:k]
        hits = [1 if rid in relevant else 0 for rid in retrieved]
        recall = sum(hits) / len(relevant) if relevant else 0.0
        precision = sum(hits) / k if k else 0.0
        dcg = sum(h / np.log2(i + 2) for i, h in enumerate(hits))
        ideal_hits = min(len(relevant), k)
        idcg = sum(1 / np.log2(i + 2) for i in range(ideal_hits))
        ndcg = dcg / idcg if idcg > 0 else 0.0
        recalls.append(recall)
        ndcgs.append(ndcg)
        precisions.append(precision)

    record["recall_at_10_mean"] = float(np.mean(recalls)) if recalls else None
    record["ndcg_at_10_mean"] = float(np.mean(ndcgs)) if ndcgs else None
    record["precision_at_10_mean"] = float(np.mean(precisions)) if precisions else None
    record["scored_query_count"] = len(recalls)
    record["query_results"] = query_results

    t0 = time.time()
    client.teardown()
    record["teardown_seconds"] = time.time() - t0

    return record


def validate_repetition(record: dict, expected_corpus: int, expected_queries: int) -> tuple:
    """Deterministic validity checks per the frozen protocol. Returns (valid, reasons)."""
    reasons = []
    if record["inserted"] != expected_corpus or record["insert_failed"] > 0:
        reasons.append(
            f"insert count mismatch: inserted={record['inserted']} failed={record['insert_failed']} expected={expected_corpus}"
        )
    if not record["index_ready"]:
        reasons.append("index did not report ready within timeout")
    if record["query_count_expected"] != expected_queries:
        reasons.append("query count mismatch")
    for qr in record["query_results"]:
        if qr["ok"] and qr["result_count"] > 10:
            reasons.append(f"top-k cardinality violation on query {qr['query_id']}: got {qr['result_count']}")
            break
    return (len(reasons) == 0, reasons)
