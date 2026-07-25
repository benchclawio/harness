from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict
from typing import Any, Callable


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def summarize_values(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "q25": quantile(values, 0.25),
        "q75": quantile(values, 0.75),
        "p95": quantile(values, 0.95),
        "p95_interpretation": "descriptive" if len(values) >= 100 else "exploratory",
    }


def bootstrap_interval(
    pairs: list[tuple[float, float]],
    estimator: Callable[[list[float]], float],
    seed: int,
    replicates: int,
    confidence_level: float,
) -> list[float] | None:
    if not pairs:
        return None
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sample = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        differences = [left - right for left, right in sample]
        estimates.append(float(estimator(differences)))
    alpha = (1 - confidence_level) / 2
    lower = quantile(estimates, alpha)
    upper = quantile(estimates, 1 - alpha)
    return [lower, upper] if lower is not None and upper is not None else None


def analyze(
    events: list[dict[str, Any]],
    seed: int,
    replicates: int,
    confidence_level: float,
) -> dict[str, Any]:
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair_subject: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for event in events:
        subject = event["subject"]["id"]
        by_subject[subject].append(event)
        by_pair_subject[event["pair"]["key"]][subject] = event

    subject_summaries: dict[str, Any] = {}
    for subject, subject_events in sorted(by_subject.items()):
        completions = sum(1 for event in subject_events if event["outcome"]["completed"])
        failure_counts = Counter(
            event["failure"]["type"] for event in subject_events if event["failure"] is not None
        )
        metrics: dict[str, Any] = {}
        for metric in ["tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"]:
            values = [
                float(event["metrics"][metric])
                for event in subject_events
                if event["metrics"][metric] is not None
            ]
            metrics[metric] = summarize_values(values)
        subject_summaries[subject] = {
            "attempts": len(subject_events),
            "completed": completions,
            "completion_rate": completions / len(subject_events),
            "completion_wilson_95": wilson_interval(completions, len(subject_events)),
            "failure_counts": dict(sorted(failure_counts.items())),
            "metrics": metrics,
        }

    subject_ids = sorted(by_subject)
    comparisons: list[dict[str, Any]] = []
    if len(subject_ids) >= 2:
        for left_index in range(len(subject_ids) - 1):
            for right_index in range(left_index + 1, len(subject_ids)):
                left = subject_ids[left_index]
                right = subject_ids[right_index]
                matched = [
                    pair for pair in by_pair_subject.values() if left in pair and right in pair
                ]
                completion_pairs = [
                    (
                        float(pair[left]["outcome"]["completed"]),
                        float(pair[right]["outcome"]["completed"]),
                    )
                    for pair in matched
                ]
                differences = [a - b for a, b in completion_pairs]
                metric_differences: dict[str, Any] = {}
                for metric in ["tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"]:
                    metric_pairs = [
                        (
                            float(pair[left]["metrics"][metric]),
                            float(pair[right]["metrics"][metric]),
                        )
                        for pair in matched
                        if pair[left]["metrics"][metric] is not None
                        and pair[right]["metrics"][metric] is not None
                    ]
                    observed = [a - b for a, b in metric_pairs]
                    metric_differences[metric] = {
                        "pairs": len(metric_pairs),
                        "median_difference_left_minus_right": statistics.median(observed)
                        if observed
                        else None,
                        "paired_bootstrap_95": bootstrap_interval(
                            metric_pairs,
                            statistics.median,
                            seed + left_index * 101 + right_index,
                            replicates,
                            confidence_level,
                        ),
                    }
                comparisons.append(
                    {
                        "left": left,
                        "right": right,
                        "matched_pairs": len(matched),
                        "completion_difference_left_minus_right": statistics.fmean(differences)
                        if differences
                        else None,
                        "completion_paired_bootstrap_95": bootstrap_interval(
                            completion_pairs,
                            statistics.fmean,
                            seed + left_index * 1009 + right_index,
                            replicates,
                            confidence_level,
                        ),
                        "discordant_left_only_success": sum(1 for a, b in completion_pairs if a == 1 and b == 0),
                        "discordant_right_only_success": sum(1 for a, b in completion_pairs if a == 0 and b == 1),
                        "metric_differences": metric_differences,
                    }
                )

    publication_eligible = all(event["publication_eligible"] for event in events)
    return {
        "schema_version": "1.0.0",
        "run_id": events[0]["run_id"],
        "publication_eligible": publication_eligible,
        "analysis": {
            "seed": seed,
            "bootstrap_replicates": replicates,
            "confidence_level": confidence_level,
            "completion_interval": "Wilson",
            "comparison": "paired percentile bootstrap",
        },
        "subjects": subject_summaries,
        "comparisons": comparisons,
        "warnings": [
            "Fixture subjects are not real frameworks; results are pipeline validation only."
        ]
        if not publication_eligible
        else [],
    }
