#!/usr/bin/env python3
"""
bc-045 analysis — herdr 0.8.0 vs tmux 3.4 vs tmux 3.7b.

Bootstrap CIs (10,000 resamples, percentile method) per arm and for each
pairwise difference. A difference is called significant only when its 95% CI
excludes zero.

Three pairs, each answering a different question:
  herdr vs tmux37b   — is herdr faster than the tmux you should be running?
  herdr vs tmux34    — is herdr faster than the tmux you probably are running?
  tmux37b vs tmux34  — how much of any gap is just an old tmux?

Usage: python3 bc045_analyze3.py <raw.jsonl> <out.json>
"""
import collections
import json
import random
import statistics
import sys

RESAMPLES = 10000
random.seed(20260807)  # fixed so the analysis reproduces exactly

ARMS = ("herdr", "tmux34", "tmux37b")
PAIRS = (("herdr", "tmux37b"), ("herdr", "tmux34"), ("tmux37b", "tmux34"))
LATENCY = ("cli_overhead_ms", "create_ms", "roundtrip_ms", "server_start_ms")


def boot_ci(values, stat=statistics.mean, resamples=RESAMPLES, alpha=0.05):
    if len(values) < 2:
        return (None, None)
    n = len(values)
    dist = []
    for _ in range(resamples):
        dist.append(stat([values[random.randrange(n)] for _ in range(n)]))
    dist.sort()
    return (dist[int((alpha / 2) * resamples)],
            dist[int((1 - alpha / 2) * resamples) - 1])


def boot_diff_ci(a, b, resamples=RESAMPLES, alpha=0.05):
    """CI for mean(a) - mean(b)."""
    if len(a) < 2 or len(b) < 2:
        return (None, None)
    na, nb = len(a), len(b)
    dist = []
    for _ in range(resamples):
        ra = statistics.mean([a[random.randrange(na)] for _ in range(na)])
        rb = statistics.mean([b[random.randrange(nb)] for _ in range(nb)])
        dist.append(ra - rb)
    dist.sort()
    return (dist[int((alpha / 2) * resamples)],
            dist[int((1 - alpha / 2) * resamples) - 1])


def describe(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "ci95": boot_ci(values),
    }


def crossover(a, b):
    """
    Session count where cumulative memory of a and b cross.
    base_a + n*marg_a == base_b + n*marg_b
    """
    if None in (a["baseline_kb"], b["baseline_kb"],
                a["marginal_kb_per_session"], b["marginal_kb_per_session"]):
        return None
    dm = a["marginal_kb_per_session"] - b["marginal_kb_per_session"]
    if abs(dm) < 1e-9:
        return None
    n = (b["baseline_kb"] - a["baseline_kb"]) / dm
    return n if n > 0 else None


def main():
    raw_path, out_path = sys.argv[1], sys.argv[2]
    rows = [json.loads(l) for l in open(raw_path) if l.strip()]

    by = collections.defaultdict(list)
    meta = {}
    for r in rows:
        if r.get("metric") == "arm_meta":
            meta[r["arm"]] = {"version": r.get("version"), "binary": r.get("binary")}
            continue
        by[(r["metric"], r["arm"])].append(r)

    report = {
        "arms": meta,
        "resamples": RESAMPLES,
        "seed": 20260807,
        "metrics": {},
        "notes": [],
    }

    # ---- continuous latency metrics -------------------------------------
    for metric in LATENCY:
        entry = {}
        vals = {}
        for arm in ARMS:
            v = [r["value"] for r in by[(metric, arm)] if r.get("value") is not None]
            vals[arm] = v
            entry[arm] = describe(v)
            failed = [r for r in by[(metric, arm)] if r.get("value") is None]
            if failed:
                entry.setdefault("failures", {})[arm] = len(failed)
        diffs = {}
        for a, b in PAIRS:
            if vals[a] and vals[b]:
                lo, hi = boot_diff_ci(vals[a], vals[b])
                diffs[f"{a}_minus_{b}"] = {
                    "mean": statistics.mean(vals[a]) - statistics.mean(vals[b]),
                    "ci95": (lo, hi),
                    "significant": (lo is not None and (lo > 0 or hi < 0)),
                }
        entry["diffs"] = diffs
        report["metrics"][metric] = entry

    # ---- survival: a proportion, and validity matters -------------------
    surv = {}
    for arm in ARMS:
        recs = by[("survive", arm)]
        valid = [r for r in recs if r.get("valid")]
        surv[arm] = {
            "reps": len(recs),
            "valid_reps": len(valid),
            "invalid_reps": len(recs) - len(valid),
            "survived": sum(r["value"] for r in valid),
            "rate": (sum(r["value"] for r in valid) / len(valid)) if valid else None,
            "server_up_after_all": all(r.get("server_up_after") for r in valid),
            "all_on_target": all(r.get("client_on_target") for r in valid),
            "lines_retained": sorted({r["lines_retained"] for r in valid}),
        }
    report["metrics"]["survive"] = surv

    # ---- memory scaling --------------------------------------------------
    scale = {}
    for arm in ARMS:
        pts = sorted(((r["sessions"], r["value"]) for r in by[("rss_kb_total", arm)]),
                     key=lambda x: x[0])
        base = dict(pts).get(0)
        per_session = None
        if len(pts) >= 2 and base is not None:
            top_n, top_v = pts[-1]
            if top_n:
                per_session = (top_v - base) / top_n
        scale[arm] = {
            "points_kb": {str(n): v for n, v in pts},
            "baseline_kb": base,
            "marginal_kb_per_session": per_session,
        }
    scale["crossover_sessions"] = {
        f"{a}_vs_{b}": crossover(scale[a], scale[b]) for a, b in PAIRS
    }
    report["metrics"]["rss_kb_total"] = scale

    report["notes"] += [
        "Each tmux arm ran on its own -L socket; RSS is scoped to that socket's "
        "server PID tree, so the two tmux versions are never pooled.",
        "roundtrip_ms includes one CLI invocation per poll; compare against "
        "cli_overhead_ms before attributing the difference to the runtime.",
        "survive counts only reps where a real client was attached, confirmed on "
        "the target session, and killed; invalid reps are excluded, not scored.",
        "Arms were interleaved per metric within a single run on one host.",
    ]

    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    # ---- console summary -------------------------------------------------
    for metric in LATENCY:
        e = report["metrics"][metric]
        print(f"\n=== {metric}")
        for arm in ARMS:
            d = e.get(arm)
            if d:
                lo, hi = d["ci95"]
                print(f"  {arm:<8} n={d['n']:<3} mean={d['mean']:8.2f} sd={d['sd']:7.2f} "
                      f"CI[{lo:.2f}, {hi:.2f}]")
        for k, v in e["diffs"].items():
            lo, hi = v["ci95"]
            print(f"    {k:<22} {v['mean']:+8.2f} CI[{lo:+.2f}, {hi:+.2f}] "
                  f"{'SIGNIFICANT' if v['significant'] else 'not significant'}")

    print("\n=== survive")
    for arm in ARMS:
        s = report["metrics"]["survive"][arm]
        print(f"  {arm:<8} {s['survived']}/{s['valid_reps']} valid ({s['invalid_reps']} "
              f"invalid) on_target={s['all_on_target']} server_up={s['server_up_after_all']}")

    print("\n=== rss")
    for arm in ARMS:
        s = report["metrics"]["rss_kb_total"][arm]
        print(f"  {arm:<8} base={s['baseline_kb']}kB "
              f"marginal={s['marginal_kb_per_session']:.0f}kB/session")
    for k, v in report["metrics"]["rss_kb_total"]["crossover_sessions"].items():
        print(f"    crossover {k:<20} {('%.1f sessions' % v) if v else 'none'}")


if __name__ == "__main__":
    main()
