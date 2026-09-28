import json, collections

evals = [json.loads(l) for l in open("bc038-eval-deepeval-v0.2.0.jsonl")]
scores = [e["raw_score"] for e in evals]
on_grid = sum(abs(s * 10 - round(s * 10)) < 1e-9 for s in scores)
print(f"evaluations: {len(scores)}, off the 0.1 grid: {len(scores) - on_grid}")

by_case = collections.defaultdict(list)
for e in evals:
    by_case[e["case_id"]].append(e["raw_score"])
same = sum(max(v) - min(v) < 1e-9 for v in by_case.values())
flips = sum(len({s >= 0.5 for s in v}) > 1 for v in by_case.values())
print(f"cases: {len(by_case)}, identical score on all 3 repeats: {same}, verdict flips at 0.5: {flips}")

ledger = [json.loads(l) for l in open("bc038-ledger-deepeval-v0.2.0.jsonl")]
steps = [c for c in ledger if c["prompt_tokens"] == 287]
print(f"step-generation calls: {len(steps)}, distinct output lengths: {len({c['completion_tokens'] for c in steps})}")
