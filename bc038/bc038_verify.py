#!/usr/bin/env python3
"""Recompute bc-038's headline numbers from the published raw records.

No network, no API key, no framework installed. It reads the hashed corpus and the four
raw JSONL files and prints the false-pass and false-fail counts that appear in the article.

    python3 bc038_verify.py
"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

CORPUS_SHA256 = "156e332faa5531d65395c17535eded75cff5dee64c395dec83bf99184bc4e1e2"
ARMS = ("naive", "phoenix", "deepeval", "opik")


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    corpus_path = base / "bc038-corpus-v0.2.0.json"

    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    print(f"corpus sha256 {digest}")
    print(f"corpus sha256 matches published value: {digest == CORPUS_SHA256}")

    cases = json.loads(corpus_path.read_text())["cases"]
    wrong = {c["case_id"] for c in cases if c["label"] == "wrong"}
    correct = {c["case_id"] for c in cases if c["label"] == "correct"}
    print(f"cases {len(cases)} = {len(wrong)} wrong + {len(correct)} correct")
    print()

    print(f"{'arm':10s} {'false pass':>12s} {'false fail':>12s} {'errors':>7s}")
    for arm in ARMS:
        rows = [
            json.loads(line)
            for line in (base / f"bc038-eval-{arm}-v0.2.0.jsonl").read_text().splitlines()
            if line.strip()
        ]
        by_case = defaultdict(list)
        errors = 0
        for row in rows:
            if row["error"] is not None or row["verdict_pass"] is None:
                errors += 1
                continue
            by_case[row["case_id"]].append(bool(row["verdict_pass"]))

        # Majority of the surviving repeats. A tie is never resolved by guessing.
        verdict = {}
        for case_id, votes in by_case.items():
            assert sum(votes) * 2 != len(votes), f"tied vote on {case_id}"
            verdict[case_id] = sum(votes) > len(votes) / 2

        fp = sum(verdict[c] for c in wrong)
        ff = sum(not verdict[c] for c in correct)
        print(f"{arm:10s} {f'{fp}/{len(wrong)}':>12s} {f'{ff}/{len(correct)}':>12s} {errors:>7d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
