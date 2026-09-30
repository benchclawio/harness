#!/usr/bin/env python3
"""Read how MLflow 3.16.1, DeepEval 4.2.7 and Phoenix evals 3.9.0 decide a trace is ready to score.

No LLM call, no network call once the wheels are on disk, no third-party import.
Usage: python3 inspect_trace_evals.py <mlflow.whl> <deepeval.whl> <phoenix_evals.whl>
"""
import ast
import hashlib
import re
import sys
import textwrap
import zipfile

EXPECTED = {
    "mlflow": ("3.16.1", "e4dfe69ceae31dfc7b8480e76ffe6a7f36752bdfac30e058e6430ade1fb5920b"),
    "deepeval": ("4.2.7", "8e325bac5a63cd90264a69ab91dd9ea0376f045d16b820193139dd56da2886bd"),
    "phoenix-evals": ("3.9.0", "425b70bcd2d87cd85a30d812adb9ddbb4b434e51de75795b67d8a4f7d20e76cd"),
}
ONLINE = "mlflow/genai/scorers/online/"


def load(path, name):
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    version, want = EXPECTED[name]
    assert digest == want, f"{name} wheel hash mismatch: {digest}"
    print(f"{name} {version} wheel sha256 {digest} OK")
    return zipfile.ZipFile(path)


def source(z, member):
    return z.read(member).decode()


def show(text, first, last, member):
    print(f"--- {member} lines {first}-{last}")
    lines = text.splitlines()
    for i in range(first, last + 1):
        print(f"{i:4d}  {lines[i - 1]}")


def method_source(text, cls, name):
    tree = ast.parse(text)
    c = next(n for n in tree.body if getattr(n, "name", None) == cls)
    f = next(n for n in c.body if getattr(n, "name", None) == name)
    return f.lineno, textwrap.dedent("\n".join(text.splitlines()[f.lineno - 1 : f.end_lineno]))


class FakeClock:
    def __init__(self, now_s):
        self.now = now_s

    def time(self):
        return self.now


class Setting:
    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v


class Window:
    def __init__(self, min_trace_timestamp_ms, max_trace_timestamp_ms):
        self.min_trace_timestamp_ms = min_trace_timestamp_ms
        self.max_trace_timestamp_ms = max_trace_timestamp_ms


class Checkpoint:
    def __init__(self, timestamp_ms, trace_id=None):
        self.timestamp_ms, self.trace_id = timestamp_ms, trace_id


def main(mlflow_whl, deepeval_whl, phoenix_whl):
    mz = load(mlflow_whl, "mlflow")
    dz = load(deepeval_whl, "deepeval")
    pz = load(phoenix_whl, "phoenix-evals")

    print("\n=== 1. MLflow: what the online scorer looks at ===")
    ck = source(mz, ONLINE + "trace_checkpointer.py")
    show(ck, 91, 110, ONLINE + "trace_checkpointer.py")
    tl = source(mz, ONLINE + "trace_loader.py")
    show(tl, 125, 131, ONLINE + "trace_loader.py")
    tp = source(mz, ONLINE + "trace_processor.py")
    show(tp, 192, 203, ONLINE + "trace_processor.py")
    show(tp, 134, 150, ONLINE + "trace_processor.py")
    consts = source(mz, ONLINE + "constants.py")
    print("--- constants.py\n" + "\n".join(l for l in consts.splitlines() if l.startswith(("MAX_", "# Max"))))

    print("\n=== 2. Does any online-scoring file mention trace status? ===")
    for member in sorted(n for n in mz.namelist() if n.startswith(ONLINE) and n.endswith(".py")):
        for i, line in enumerate(source(mz, member).splitlines(), 1):
            if re.search(r"IN_PROGRESS|\.status|TraceState|trace_status", line):
                print(f"{member.split('/')[-1]}:{i}: {line.strip()}")
    print("(no output above means no status check in any online-scoring file)")
    env = source(mz, "mlflow/environment_variables.py")
    i = env.index("MLFLOW_ONLINE_SCORING_DEFAULT_TRACE_COMPLETION_BUFFER_SECONDS")
    print("--- environment_variables.py docstring for the trace buffer")
    print("\n".join(env[:i].splitlines()[-5:]))

    print("\n=== 3. Run MLflow's own calculate_time_window on a fake clock ===")
    _, seg = method_source(ck, "OnlineTraceCheckpointManager", "calculate_time_window")
    _, get_seg = method_source(ck, "OnlineTraceCheckpointManager", "get_checkpoint")

    def window_at(now_s, checkpoint):
        ns = {
            "time": FakeClock(now_s),
            "MLFLOW_ONLINE_SCORING_DEFAULT_TRACE_COMPLETION_BUFFER_SECONDS": Setting(300),
            "MAX_LOOKBACK_MS": 3_600_000,
            "OnlineTraceScoringTimeWindow": Window,
        }
        exec(seg.replace("self.get_checkpoint()", "CKPT"), {**ns, "CKPT": checkpoint}, ns)
        return ns["calculate_time_window"](type("M", (), {"get_checkpoint": lambda s: checkpoint})())

    T0 = 1_000_000  # trace start, seconds on the fake clock
    POLL = 60       # ASSUMPTION: the job runs every 60 s; the wheel does not fix an interval
    print(f"trace starts at t={T0}s, scorer polls every {POLL}s (assumed), buffer 300s (default)")
    print(f"{'trace runs for':>16}  {'earliest score':>14}  {'state when scored':>18}")
    for dur in (60, 240, 300, 360, 600, 1800):
        now = T0
        while True:
            now += POLL
            w = window_at(now, Checkpoint(T0 * 1000 - 1))
            if w.min_trace_timestamp_ms <= T0 * 1000 <= w.max_trace_timestamp_ms:
                break
        state = "COMPLETE" if T0 + dur <= now else "IN_PROGRESS"
        print(f"{dur:>14}s  {'+' + str(now - T0) + 's':>10}  {state:>18}")

    print("\nAfter scoring the checkpoint sits on the trace's start time. Re-typed from lines 195-203:")
    cp = Checkpoint(T0 * 1000, "trace-b")
    infos = [(T0 * 1000, "trace-a"), (T0 * 1000, "trace-b"), (T0 * 1000, "trace-c")]
    kept = [t for t in infos if not (t[0] == cp.timestamp_ms and t[1] <= cp.trace_id)]
    print(f"checkpoint=(t0, trace-b) -> candidates {[i[1] for i in infos]} -> rescored {[i[1] for i in kept]}")
    w = window_at(T0 + 3600, cp)
    print(f"later window min == checkpoint start? {w.min_trace_timestamp_ms == cp.timestamp_ms} "
          f"(trace-b itself is filtered by trace_id; nothing re-selects it)")

    print("\n=== 4. Outage longer than the lookback: traces are dropped, not queued ===")
    old = Checkpoint(T0 * 1000)
    w = window_at(T0 + 3 * 3600, old)
    skipped = (w.min_trace_timestamp_ms - T0 * 1000) / 1000
    print(f"checkpoint at t0, scorer resumes 3 h later -> window starts {skipped:.0f}s ({skipped / 3600:.2f} h) after the checkpoint")
    print("traces that started inside that gap are outside every future window")

    print("\n=== 5. DeepEval 4.2.7 ===")
    ts = source(dz, "deepeval/evaluate/execute/trace_scope.py")
    show(ts, 67, 71, "deepeval/evaluate/execute/trace_scope.py")
    show(ts, 88, 90, "deepeval/evaluate/execute/trace_scope.py")
    of = source(dz, "deepeval/tracing/offline_evals/trace.py")
    show(of, 6, 8, "deepeval/tracing/offline_evals/trace.py")
    show(of, 15, 34, "deepeval/tracing/offline_evals/trace.py")
    win = [m for m in dz.namelist() if m.startswith("deepeval/tracing/offline_evals/") and m.endswith(".py")]
    hits = [(m, i) for m in win for i, l in enumerate(source(dz, m).splitlines(), 1)
            if re.search(r"inactiv|completion.?buffer|lookback|quiet", l, re.I)]
    print(f"buffer/inactivity/lookback logic in offline_evals/: {hits or 'none'}")

    print("\n=== 6. Phoenix evals 3.9.0 ===")
    ev = source(pz, "phoenix/evals/evaluators.py")
    show(ev, 273, 281, "phoenix/evals/evaluators.py")
    show(ev, 383, 387, "phoenix/evals/evaluators.py")
    pat = re.compile(r"IN_PROGRESS|\bend_time\b|inactivity|completion.?buffer|lookback")
    total = [(m, i) for m in pz.namelist() if m.endswith(".py")
             for i, l in enumerate(source(pz, m).splitlines(), 1) if pat.search(l)]
    print(f"trace-completion terms anywhere in phoenix-evals: {total or 'none'}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
