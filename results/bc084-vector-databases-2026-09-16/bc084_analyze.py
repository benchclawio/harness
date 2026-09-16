import json
import numpy as np

records = []
with open("/root/bc084/scored-results-raw.jsonl") as f:
    for line in f:
        records.append(json.loads(line))

subjects = sorted(set(r["subject"] for r in records))

print("=== per-subject summary (n=20 each) ===")
summary = {}
for s in subjects:
    subj_records = [r for r in records if r["subject"] == s]
    assert len(subj_records) == 20, f"{s}: {len(subj_records)}"
    assert all(r["valid"] for r in subj_records), f"{s} has invalid reps"

    recalls = np.array([r["recall_at_10_mean"] for r in subj_records])
    ndcgs = np.array([r["ndcg_at_10_mean"] for r in subj_records])
    precisions = np.array([r["precision_at_10_mean"] for r in subj_records])
    insert_s = np.array([r["insert_seconds"] for r in subj_records])
    setup_s = np.array([r["setup_seconds"] for r in subj_records])
    ready_s = np.array([r["index_ready_seconds"] for r in subj_records])
    failed_q = np.array([r["failed_queries"] for r in subj_records])

    all_latencies = []
    for r in subj_records:
        all_latencies.extend(r["query_latencies_s"])
    all_latencies = np.array(all_latencies) * 1000  # ms

    summary[s] = {
        "recall_at_10_mean": float(recalls.mean()),
        "recall_at_10_std": float(recalls.std()),
        "ndcg_at_10_mean": float(ndcgs.mean()),
        "ndcg_at_10_std": float(ndcgs.std()),
        "precision_at_10_mean": float(precisions.mean()),
        "total_failed_queries": int(failed_q.sum()),
        "index_build_seconds_median": float(np.median(insert_s + setup_s)),
        "index_build_seconds_p95": float(np.percentile(insert_s + setup_s, 95)),
        "query_latency_ms_median": float(np.median(all_latencies)),
        "query_latency_ms_p95": float(np.percentile(all_latencies, 95)),
        "query_latency_ms_min": float(all_latencies.min()),
        "query_latency_ms_max": float(all_latencies.max()),
        "n_query_observations": len(all_latencies),
    }
    print(s, json.dumps(summary[s], indent=2))

print("\n=== paired bootstrap: recall@10 differences vs qdrant (baseline) ===")
baseline = "qdrant"
baseline_recalls_by_rep = {}
for r in records:
    if r["subject"] == baseline:
        baseline_recalls_by_rep[r["rep_index"]] = r["recall_at_10_mean"]

rng = np.random.default_rng(42)
n_boot = 10000
comparisons = {}
for s in subjects:
    if s == baseline:
        continue
    subj_recalls_by_rep = {r["rep_index"]: r["recall_at_10_mean"] for r in records if r["subject"] == s}
    reps = sorted(subj_recalls_by_rep.keys())
    diffs = np.array([subj_recalls_by_rep[i] - baseline_recalls_by_rep[i] for i in reps])
    boot_means = []
    for _ in range(n_boot):
        sample = rng.choice(diffs, size=len(diffs), replace=True)
        boot_means.append(sample.mean())
    boot_means = np.array(boot_means)
    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
    mean_diff = diffs.mean()
    excludes_zero = ci_lo > 0 or ci_hi < 0
    practical = abs(mean_diff) >= 0.02
    comparisons[s] = {
        "mean_diff_vs_qdrant": float(mean_diff),
        "ci95_lo": float(ci_lo),
        "ci95_hi": float(ci_hi),
        "excludes_zero": bool(excludes_zero),
        "practical_threshold_met": bool(practical),
        "verdict": "practical difference" if (excludes_zero and practical) else "no practical difference",
    }
    print(s, "vs", baseline, json.dumps(comparisons[s], indent=2))

with open("/root/bc084/analysis-summary.json", "w") as f:
    json.dump({"per_subject": summary, "vs_qdrant_bootstrap": comparisons}, f, indent=2)
print("\nWritten to /root/bc084/analysis-summary.json")
