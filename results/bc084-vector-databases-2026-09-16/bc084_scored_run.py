"""Scored run: 20 fresh-index repetitions per subject, interleaved order,
one subject's container active at a time. Frozen protocol per
methodology/vector-databases-v0.1.0.md and the 2026-09-09 run plan.
"""
import json
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, "/root/bc084")
from bc084_harness import run_repetition, validate_repetition
from bc084_adapters import QdrantAdapter, WeaviateAdapter, ChromaAdapter, PineconeAdapter

N_REPS = 20
WARMUP_PASSES = 3
K = 10

CONTAINER_SPECS = {
    "qdrant": {
        "run": [
            "docker", "run", "-d", "--name", "qdrant-scored",
            "-p", "127.0.0.1:6333:6333", "qdrant/qdrant:v1.19.1",
        ],
        "boot_wait_s": 5,
        "adapter": QdrantAdapter,
    },
    "weaviate": {
        "run": [
            "docker", "run", "-d", "--name", "weaviate-scored",
            "-p", "127.0.0.1:8080:8080", "-p", "127.0.0.1:50051:50051",
            "-e", "QUERY_DEFAULTS_LIMIT=25",
            "-e", "AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true",
            "-e", "PERSISTENCE_DATA_PATH=/var/lib/weaviate",
            "-e", "DEFAULT_VECTORIZER_MODULE=none",
            "semitechnologies/weaviate:1.39.5",
        ],
        "boot_wait_s": 10,
        "adapter": WeaviateAdapter,
    },
    "chroma": {
        "run": [
            "docker", "run", "-d", "--name", "chroma-scored",
            "-p", "127.0.0.1:8000:8000", "chromadb/chroma:1.5.9",
        ],
        "boot_wait_s": 8,
        "adapter": ChromaAdapter,
    },
    "pinecone": {
        "run": [
            "docker", "run", "-d", "--name", "pinecone-scored",
            "-p", "127.0.0.1:5080-5089:5080-5089",
            "-e", "PORT=5080", "-e", "PINECONE_HOST=localhost",
            "ghcr.io/pinecone-io/pinecone-local:latest",
        ],
        "boot_wait_s": 8,
        "adapter": PineconeAdapter,
    },
}

SUBJECT_ORDER = ["qdrant", "weaviate", "chroma", "pinecone"]

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


def container_name(subject):
    return CONTAINER_SPECS[subject]["run"][4]


def start_container(subject):
    spec = CONTAINER_SPECS[subject]
    subprocess.run(["docker", "rm", "-f", container_name(subject)], capture_output=True)
    subprocess.run(spec["run"], check=True, capture_output=True)
    time.sleep(spec["boot_wait_s"])


def stop_container(subject):
    name = container_name(subject)
    subprocess.run(["docker", "stop", name], capture_output=True)
    subprocess.run(["docker", "rm", name], capture_output=True)


results = []
run_log = []
run_started = time.time()

for rep in range(N_REPS):
    for subject in SUBJECT_ORDER:
        t_container_start = time.time()
        start_container(subject)
        client = CONTAINER_SPECS[subject]["adapter"]()
        try:
            record = run_repetition(
                client,
                corpus_ids,
                corpus_vectors,
                query_ids,
                query_vectors,
                qrels,
                k=K,
                scored=True,
                rep_index=rep,
                warmup_passes=WARMUP_PASSES,
            )
            if hasattr(client, "close"):
                client.close()
            valid, reasons = validate_repetition(record, len(corpus_ids), len(query_ids))
            record["valid"] = valid
            record["invalid_reasons"] = reasons
        except Exception as e:  # noqa: BLE001 - a whole-repetition failure is recorded, not fatal
            record = {
                "subject": subject,
                "rep_index": rep,
                "scored": True,
                "valid": False,
                "invalid_reasons": [f"repetition exception: {type(e).__name__}: {e}"],
            }
        finally:
            stop_container(subject)

        elapsed = time.time() - t_container_start
        results.append(record)
        log_line = {
            "rep": rep,
            "subject": subject,
            "valid": record.get("valid"),
            "recall_at_10": record.get("recall_at_10_mean"),
            "elapsed_s": round(elapsed, 1),
        }
        run_log.append(log_line)
        print(json.dumps(log_line))

        with open("/root/bc084/scored-results-raw.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")

total_elapsed = time.time() - run_started
print(json.dumps({"total_elapsed_s": round(total_elapsed, 1), "total_repetitions": len(results)}))

with open("/root/bc084/scored-run-log.json", "w") as f:
    json.dump(run_log, f, indent=2)
