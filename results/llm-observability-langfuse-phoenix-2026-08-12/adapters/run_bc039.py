#!/usr/bin/env python3
"""bc-039 scored run driver.

Arms are interleaved round by round — control, langfuse, phoenix, then round two — so no arm
owns a contiguous block of wall-clock time. API latency drifts, and a block design would let
that drift land entirely on one arm and be read as overhead.

Usage:
    python3 run_bc039.py <rounds> <out_prefix>
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bc039_arms as arms  # noqa: E402
import bc039_capture as capture  # noqa: E402
import bc039_exporters as exporters  # noqa: E402
from bc039_runner import ROOT, run_workload  # noqa: E402

MODEL = "gpt-4o"
PRICE_IN = 2.50 / 1_000_000
PRICE_OUT = 10.00 / 1_000_000

LANGFUSE_HOST = "http://127.0.0.1:3000"
PHOENIX_BASE = "http://127.0.0.1:6006"
PHOENIX_OTLP = "http://127.0.0.1:6006/v1/traces"
PHOENIX_PROJECT = "bc039"

SUITE = json.loads((ROOT / "methodology/bc039-workload-v0.1.0.json").read_text())


def make_model_caller(client, usage_accumulator):
    def call_model(prompt, context):
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=16,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        tokens_in = usage.prompt_tokens or 0
        tokens_out = usage.completion_tokens or 0
        usage_accumulator["tokens_in"] += tokens_in
        usage_accumulator["tokens_out"] += tokens_out
        usage_accumulator["requests"] += 1
        return {
            "text": (response.choices[0].message.content or "").strip(),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    return call_model


def main():
    rounds = int(sys.argv[1])
    prefix = sys.argv[2]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key, max_retries=0, timeout=90.0)

    lf_public = os.environ["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"]
    lf_secret = os.environ["LANGFUSE_INIT_PROJECT_SECRET_KEY"]

    tracers = {
        "control": arms.ControlTracer(),
        "langfuse": arms.build_langfuse_tracer(LANGFUSE_HOST, lf_public, lf_secret),
        "phoenix": arms.build_phoenix_tracer(PHOENIX_OTLP, PHOENIX_PROJECT),
    }
    readers = {
        "langfuse": lambda: exporters.read_langfuse(LANGFUSE_HOST, lf_public, lf_secret),
        "phoenix": lambda: exporters.read_phoenix(PHOENIX_BASE, PHOENIX_PROJECT),
    }

    # Positive control gates FIRST. An arm that fails does not run.
    gates = {}
    for name, reader in readers.items():
        gates[name] = arms.positive_control(tracers[name], reader)
        print(f"positive control {name}: {json.dumps(gates[name])}", flush=True)
    failed = [n for n, g in gates.items() if not g["passed"]]
    if failed:
        raise SystemExit(f"positive control failed for {failed}; refusing to run")

    raw_path = Path(f"{prefix}-raw.jsonl")
    issued_by_arm = {name: [] for name in tracers}
    session_id = uuid.uuid4().hex[:8]

    with raw_path.open("w") as handle:
        for round_index in range(rounds):
            for arm_name, tracer in tracers.items():
                usage = {"tokens_in": 0, "tokens_out": 0, "requests": 0}
                run_id = f"{session_id}-{arm_name}-r{round_index:03d}"
                started = time.monotonic()
                result = run_workload(
                    tracer,
                    make_model_caller(client, usage),
                    suite=SUITE,
                    run_id=run_id,
                )
                elapsed = time.monotonic() - started
                issued_by_arm[arm_name].extend(result["issued"])
                record = {
                    "arm": arm_name,
                    "round": round_index,
                    "run_id": run_id,
                    "wall_time_s": round(elapsed, 4),
                    "issued_counts": result["issued_counts"],
                    "provider_tokens_in": usage["tokens_in"],
                    "provider_tokens_out": usage["tokens_out"],
                    "provider_requests": usage["requests"],
                    "cost_usd": round(usage["tokens_in"] * PRICE_IN + usage["tokens_out"] * PRICE_OUT, 8),
                    "outputs": [o for sc in result["scenarios"] for o in sc["outputs"]],
                }
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                print(f"round {round_index} {arm_name} {elapsed:.2f}s", flush=True)

    # Declared flush window, applied identically to every arm.
    for tracer in tracers.values():
        tracer.flush()
    print(f"flushing, waiting {arms.FLUSH_WINDOW_S}s", flush=True)
    time.sleep(arms.FLUSH_WINDOW_S)

    reports = {}
    for arm_name, reader in readers.items():
        exported = reader()
        reports[arm_name] = capture.compare(issued_by_arm[arm_name], exported)
        reports[arm_name]["exported_record_count"] = len(exported)
        print(f"read back {arm_name}: {len(exported)} records", flush=True)

    summary = {
        "session_id": session_id,
        "model": MODEL,
        "rounds": rounds,
        "suite_version": SUITE["suite_version"],
        "positive_control": gates,
        "flush_window_s": arms.FLUSH_WINDOW_S,
        "capture": reports,
        "issued_totals": {name: capture_counts(issued_by_arm[name]) for name in issued_by_arm},
    }
    Path(f"{prefix}-capture.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"raw": str(raw_path), "capture": f"{prefix}-capture.json"}, indent=2))


def capture_counts(issued):
    from bc039_runner import count_issued

    return count_issued(issued)


if __name__ == "__main__":
    main()
