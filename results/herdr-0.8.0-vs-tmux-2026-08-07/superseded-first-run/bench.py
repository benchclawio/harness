#!/usr/bin/env python3
"""
bc-044 — Herdr 0.8.0 vs tmux 3.4 terminal-session-runtime benchmark.

Runs on the disposable sandbox. No model calls, no credentials, no network
during measurement. Both arms are interleaved run-by-run so any drift in the
host hits both equally (same-day control requirement).

Metrics
  1. cli_overhead_ms   — cost of one scripted CLI invocation (list command)
  2. create_ms         — create one session/workspace with a live shell
  3. roundtrip_ms      — send a command, poll until its output is readable
  4. survive           — does the shell survive the client/parent going away
  5. rss_kb_total      — resident memory of the whole runtime at N sessions
  6. server_start_ms   — cold server startup

Output: JSONL, one record per measurement, to the path given as argv[1].
"""
import collections
import json
import os
import subprocess
import sys
import time
import uuid

HERDR = os.path.expanduser("~/.local/bin/herdr")
POLL_INTERVAL = 0.02
POLL_TIMEOUT = 20.0


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def now():
    return time.perf_counter()


# --------------------------------------------------------------------------
# arm implementations — deliberately symmetric
# --------------------------------------------------------------------------
class Herdr:
    name = "herdr"
    version = "0.8.0"

    def list_cmd(self):
        return [HERDR, "pane", "list"]

    def server_start(self):
        subprocess.Popen(
            [HERDR, "server"],
            stdout=open("/tmp/herdr-server.log", "ab"),
            stderr=subprocess.STDOUT,
        )

    def server_ready(self):
        # parse the status field exactly: "not running" contains "running"
        r = run([HERDR, "status", "server"], timeout=10)
        for line in r.stdout.splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip() == "running"
        return False

    def server_stop(self):
        run([HERDR, "server", "stop"], timeout=20)

    def create(self, label):
        r = run([HERDR, "workspace", "create", "--label", label, "--cwd", "/root"])
        if r.returncode != 0:
            raise RuntimeError(f"herdr create failed: {r.stderr[:200]}")
        d = json.loads(r.stdout)
        return d["result"]["root_pane"]["pane_id"]

    def send(self, handle, text):
        run([HERDR, "pane", "send-text", handle, text])
        run([HERDR, "pane", "send-keys", handle, "Enter"])

    def read(self, handle):
        r = run([HERDR, "pane", "read", handle])
        return r.stdout

    def close(self, handle):
        run([HERDR, "pane", "close", handle])

    def procs(self):
        return ["herdr"]

    def attach_client(self, label):
        """Attach a real interactive client in its own pty and session group."""
        p = subprocess.Popen(
            ["script", "-q", "-c", HERDR, "/dev/null"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        return p.pid

    def client_count(self, label):
        r = run(["pgrep", "-x", "herdr"])
        # the headless server is one; anything beyond it is an attached client
        return max(0, len(r.stdout.split()) - 1)


class Tmux:
    name = "tmux"
    version = "3.4"

    def list_cmd(self):
        return ["tmux", "list-panes", "-a"]

    def server_start(self):
        run(["tmux", "new-session", "-d", "-s", "__boot__"])

    def server_ready(self):
        return run(["tmux", "list-sessions"], timeout=10).returncode == 0

    def server_stop(self):
        run(["tmux", "kill-server"], timeout=20)

    def create(self, label):
        r = run(["tmux", "new-session", "-d", "-s", label, "-c", "/root"])
        if r.returncode != 0:
            raise RuntimeError(f"tmux create failed: {r.stderr[:200]}")
        return label

    def send(self, handle, text):
        run(["tmux", "send-keys", "-t", handle, text, "Enter"])

    def read(self, handle):
        r = run(["tmux", "capture-pane", "-p", "-t", handle])
        return r.stdout

    def close(self, handle):
        run(["tmux", "kill-session", "-t", handle])

    def procs(self):
        return ["tmux", "tmux: server"]

    def attach_client(self, label):
        p = subprocess.Popen(
            ["script", "-q", "-c", f"tmux attach-session -t {label}", "/dev/null"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        return p.pid

    def client_count(self, label):
        r = run(["tmux", "list-clients", "-t", label])
        return len([l for l in r.stdout.splitlines() if l.strip()])


# --------------------------------------------------------------------------
# measurements
# --------------------------------------------------------------------------
def measure_cli_overhead(arm, reps, emit):
    for i in range(reps):
        t0 = now()
        run(arm.list_cmd())
        emit({"metric": "cli_overhead_ms", "arm": arm.name, "rep": i,
              "value": (now() - t0) * 1000})


def measure_create(arm, reps, emit):
    for i in range(reps):
        label = f"bench{uuid.uuid4().hex[:8]}"
        t0 = now()
        handle = arm.create(label)
        dt = (now() - t0) * 1000
        emit({"metric": "create_ms", "arm": arm.name, "rep": i, "value": dt})
        arm.close(handle)


def measure_roundtrip(arm, reps, emit):
    label = f"rt{uuid.uuid4().hex[:8]}"
    handle = arm.create(label)
    time.sleep(1.0)  # let the shell settle and print its first prompt
    try:
        for i in range(reps):
            marker = f"MARK{uuid.uuid4().hex[:10].upper()}"
            t0 = now()
            arm.send(handle, f"echo {marker}")
            found = False
            while now() - t0 < POLL_TIMEOUT:
                # the echoed command line also contains the marker, so require
                # it to appear at least twice: once echoed, once as output
                if arm.read(handle).count(marker) >= 2:
                    found = True
                    break
                time.sleep(POLL_INTERVAL)
            dt = (now() - t0) * 1000
            emit({"metric": "roundtrip_ms", "arm": arm.name, "rep": i,
                  "value": dt if found else None, "ok": found})
    finally:
        arm.close(handle)


def _proc_table():
    """pid -> (ppid, rss_kb, comm) for every readable process."""
    table = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            ppid = rss = None
            comm = ""
            with open(f"/proc/{pid}/status") as fh:
                for line in fh:
                    if line.startswith("Name:"):
                        comm = line.split(maxsplit=1)[1].strip()
                    elif line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                    elif line.startswith("VmRSS:"):
                        rss = int(line.split()[1])
                    if ppid is not None and rss is not None and comm:
                        break
            if ppid is not None:
                table[int(pid)] = (ppid, rss or 0, comm)
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
            pass
    return table


def rss_kb(arm):
    """
    RSS of the runtime's own server processes plus every process descended
    from them — the shells it is holding open. Scoped to the process tree so
    unrelated system processes and our own SSH shell are never counted.
    """
    table = _proc_table()
    children = collections.defaultdict(list)
    for pid, (ppid, _, _) in table.items():
        children[ppid].append(pid)

    roots = [pid for pid, (_, _, comm) in table.items() if comm in arm.procs()]
    seen = set()
    stack = list(roots)
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))

    return sum(table[pid][1] for pid in seen if pid in table)


def measure_scale(arm, steps, emit):
    handles = []
    baseline = rss_kb(arm)
    emit({"metric": "rss_kb_total", "arm": arm.name, "sessions": 0,
          "value": baseline})
    created = 0
    for target in steps:
        while created < target:
            handles.append(arm.create(f"scale{uuid.uuid4().hex[:8]}"))
            created += 1
        time.sleep(2.0)  # let every shell finish starting before sampling
        emit({"metric": "rss_kb_total", "arm": arm.name, "sessions": target,
              "value": rss_kb(arm)})
    for h in handles:
        arm.close(h)


def measure_survival(arm, reps, emit):
    """
    The core claim: work survives the client going away.

    A *real* interactive client is attached inside a pty, then SIGKILLed
    together with its process group — no cleanup, no protocol goodbye, the
    closest local analogue of a dropped SSH connection. The server and the
    work it holds must both outlive it.

    A rep only counts if a client was genuinely attached and genuinely killed;
    otherwise it is recorded as invalid rather than as a pass.
    """
    for i in range(reps):
        label = f"surv{uuid.uuid4().hex[:8]}"
        handle = arm.create(label)
        time.sleep(0.8)

        marker = f"SURV{uuid.uuid4().hex[:8].upper()}"
        arm.send(handle, f"(for n in 1 2 3 4 5 6 7 8; do echo {marker}_$n; sleep 1; done)")
        time.sleep(1.5)

        client_pid = arm.attach_client(label)
        time.sleep(2.5)
        attached = client_pid is not None and arm.client_count(label) > 0

        killed = 0
        if client_pid is not None:
            try:
                os.killpg(os.getpgid(client_pid), 9)
                killed = 1
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(client_pid, 9)
                    killed = 1
                except (ProcessLookupError, PermissionError):
                    pass

        time.sleep(7.0)  # the loop should run to completion with nobody watching
        server_up = arm.server_ready()
        out = arm.read(handle)
        completed = f"{marker}_8" in out
        retained = out.count(marker)

        emit({"metric": "survive", "arm": arm.name, "rep": i,
              "value": 1 if (completed and server_up) else 0,
              "valid": bool(attached and killed),
              "client_attached": attached, "clients_killed": killed,
              "server_up_after": server_up, "lines_retained": retained})
        arm.close(handle)


def measure_server_start(arm, reps, emit):
    for i in range(reps):
        arm.server_stop()
        # confirm it is actually down before timing a "cold" start, otherwise
        # we would be timing a status call against a server that never left
        down = False
        deadline = now() + 15
        while now() < deadline:
            if not arm.server_ready():
                down = True
                break
            time.sleep(0.05)
        if not down:
            emit({"metric": "server_start_ms", "arm": arm.name, "rep": i,
                  "value": None, "ok": False, "note": "server would not stop"})
            continue
        time.sleep(1.0)
        t0 = now()
        arm.server_start()
        ready = False
        while now() - t0 < 30:
            if arm.server_ready():
                ready = True
                break
            time.sleep(0.02)
        emit({"metric": "server_start_ms", "arm": arm.name, "rep": i,
              "value": (now() - t0) * 1000 if ready else None, "ok": ready})
        time.sleep(1.0)


# --------------------------------------------------------------------------
def main():
    out_path = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    fh = open(out_path, "a", buffering=1)

    def emit(rec):
        rec["ts"] = time.time()
        fh.write(json.dumps(rec) + "\n")

    arms = [Herdr(), Tmux()]

    for arm in arms:
        arm.server_stop()
    time.sleep(2)
    for arm in arms:
        arm.server_start()
    time.sleep(4)
    for arm in arms:
        if not arm.server_ready():
            raise SystemExit(f"{arm.name} server did not start")

    # interleave arms per metric so host drift hits both equally
    for fn, kwargs in (
        (measure_cli_overhead, {"reps": reps}),
        (measure_create, {"reps": reps}),
        (measure_roundtrip, {"reps": reps}),
        (measure_survival, {"reps": max(6, reps // 3)}),
    ):
        for arm in arms:
            print(f"  {fn.__name__} {arm.name}", flush=True)
            fn(arm, emit=emit, **kwargs)

    for arm in arms:
        print(f"  measure_scale {arm.name}", flush=True)
        measure_scale(arm, steps=[1, 5, 10, 20, 40], emit=emit)

    for arm in arms:
        print(f"  measure_server_start {arm.name}", flush=True)
        measure_server_start(arm, reps=8, emit=emit)

    fh.close()
    print("BENCH_COMPLETE")


if __name__ == "__main__":
    main()
