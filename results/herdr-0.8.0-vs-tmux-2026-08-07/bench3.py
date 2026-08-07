#!/usr/bin/env python3
"""
bc-045 — three-arm terminal-session-runtime benchmark.

  herdr 0.8.0            ~/.local/bin/herdr
  tmux 3.4               /usr/bin/tmux            (Ubuntu 24.04 LTS default)
  tmux 3.7b              /opt/tmux37b/bin/tmux    (current, built from source)

Why three arms: the first run compared herdr against the distro tmux, which is
2.5 years and four releases old. Upstream tmux optimised the exact paths we
measure (getpwuid caching off the startup path, issue 4973; a fork race in pane
creation, issue 4719), all in herdr's disfavour. Running both tmux versions on
the same box on the same day separates "herdr is faster" from "the tmux you
have is old".

Isolation notes that matter for correctness:
  * Each tmux arm gets its own `-L` socket, so the two servers never share
    state. Without this they would be the same server.
  * RSS is scoped to each arm's own server PID tree. Comm-name matching would
    sum both tmux servers together, since both are named "tmux: server".
  * Survival uses the corrected (v2) scoping: the workspace under test is
    focused before the client attaches, and each rep is gated on the server
    snapshot confirming the client is really on that workspace.

No model calls, no credentials, no network during measurement.
Output: JSONL, one record per measurement, to argv[1].
"""
import collections
import json
import os
import subprocess
import sys
import time
import uuid

HERDR = os.path.expanduser("~/.local/bin/herdr")
TMUX34 = "/usr/bin/tmux"
TMUX37B = "/opt/tmux37b/bin/tmux"
POLL_INTERVAL = 0.02
POLL_TIMEOUT = 20.0


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def now():
    return time.perf_counter()


# --------------------------------------------------------------------------
# arms — deliberately symmetric
# --------------------------------------------------------------------------
class Herdr:
    name = "herdr"
    version = "0.8.0"
    binary = HERDR

    def list_cmd(self):
        return [HERDR, "pane", "list"]

    def server_start(self):
        subprocess.Popen([HERDR, "server"],
                         stdout=open("/tmp/herdr-server.log", "ab"),
                         stderr=subprocess.STDOUT)

    def server_ready(self):
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
        return json.loads(r.stdout)["result"]["root_pane"]["pane_id"]

    def send(self, handle, text):
        run([HERDR, "pane", "send-text", handle, text])
        run([HERDR, "pane", "send-keys", handle, "Enter"])

    def read(self, handle):
        return run([HERDR, "pane", "read", handle]).stdout

    def close(self, handle):
        run([HERDR, "pane", "close", handle])

    def root_pids(self):
        """Every live herdr process — the server, plus clients if attached."""
        r = run(["pgrep", "-x", "herdr"])
        return [int(p) for p in r.stdout.split() if p.strip()]

    # --- survival helpers (corrected scoping) ---
    def focus(self, handle):
        run([HERDR, "workspace", "focus", handle.split(":")[0]])

    def focused_workspace(self):
        r = run([HERDR, "api", "snapshot"], timeout=15)
        try:
            return json.loads(r.stdout)["result"]["snapshot"]["focused_workspace_id"]
        except Exception:
            return None

    def attach_client(self, handle, label):
        # bare `herdr` attaches to the FOCUSED workspace, so focus first
        self.focus(handle)
        p = subprocess.Popen(["script", "-q", "-c", HERDR, "/dev/null"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, start_new_session=True,
                             env={**os.environ, "TERM": "xterm-256color"})
        return p.pid

    def client_on_target(self, handle, label):
        return self.focused_workspace() == handle.split(":")[0]

    def client_count(self, label):
        return max(0, len(self.root_pids()) - 1)


class Tmux:
    """One tmux version on its own socket."""

    def __init__(self, name, version, binary, socket):
        self.name = name
        self.version = version
        self.binary = binary
        self.socket = socket

    def _t(self, *args):
        return [self.binary, "-L", self.socket, *args]

    def list_cmd(self):
        return self._t("list-panes", "-a")

    def server_start(self):
        run(self._t("new-session", "-d", "-s", "__boot__"))

    def server_ready(self):
        return run(self._t("list-sessions"), timeout=10).returncode == 0

    def server_stop(self):
        run(self._t("kill-server"), timeout=20)

    def create(self, label):
        r = run(self._t("new-session", "-d", "-s", label, "-c", "/root"))
        if r.returncode != 0:
            raise RuntimeError(f"{self.name} create failed: {r.stderr[:200]}")
        return label

    def send(self, handle, text):
        run(self._t("send-keys", "-t", handle, text, "Enter"))

    def read(self, handle):
        return run(self._t("capture-pane", "-p", "-t", handle)).stdout

    def close(self, handle):
        run(self._t("kill-session", "-t", handle))

    def root_pids(self):
        """This socket's server PID only — never the other tmux version's."""
        r = run(self._t("display-message", "-p", "#{pid}"), timeout=10)
        try:
            return [int(r.stdout.strip())]
        except ValueError:
            return []

    # --- survival helpers ---
    def attach_client(self, handle, label):
        p = subprocess.Popen(
            ["script", "-q", "-c",
             f"{self.binary} -L {self.socket} attach-session -t {label}", "/dev/null"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color"})
        return p.pid

    def client_on_target(self, handle, label):
        # attach-session -t names the session directly, so an attached client
        # is by construction on the target
        return self.client_count(label) > 0

    def client_count(self, label):
        r = run(self._t("list-clients", "-t", label))
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
    time.sleep(1.0)
    try:
        for i in range(reps):
            marker = f"MARK{uuid.uuid4().hex[:10].upper()}"
            t0 = now()
            arm.send(handle, f"echo {marker}")
            found = False
            while now() - t0 < POLL_TIMEOUT:
                # the echoed command line also contains the marker, so require
                # two occurrences: once echoed, once as real output
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
    RSS of this arm's own server process plus every process descended from it.
    Roots come from the arm itself (tmux: this socket's server PID), never from
    a comm-name match — both tmux versions are called "tmux: server" and would
    otherwise be summed together.
    """
    table = _proc_table()
    children = collections.defaultdict(list)
    for pid, (ppid, _, _) in table.items():
        children[ppid].append(pid)

    seen = set()
    stack = [p for p in arm.root_pids() if p in table]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))

    return sum(table[pid][1] for pid in seen if pid in table)


def measure_scale(arm, steps, emit):
    handles = []
    emit({"metric": "rss_kb_total", "arm": arm.name, "sessions": 0,
          "value": rss_kb(arm)})
    created = 0
    for target in steps:
        while created < target:
            handles.append(arm.create(f"scale{uuid.uuid4().hex[:8]}"))
            created += 1
        time.sleep(2.0)
        emit({"metric": "rss_kb_total", "arm": arm.name, "sessions": target,
              "value": rss_kb(arm)})
    for h in handles:
        arm.close(h)


def measure_survival(arm, reps, emit):
    """
    A real interactive client is attached inside a pty, then SIGKILLed with its
    process group — no cleanup, no protocol goodbye, the closest local analogue
    of a dropped SSH connection. The server and its work must both outlive it.

    A rep counts only if a client was genuinely attached, genuinely ON THE
    WORKSPACE UNDER TEST, and genuinely killed. Otherwise it is invalid, not a
    pass. The missing on-target gate is what invalidated the first run.
    """
    for i in range(reps):
        label = f"surv{uuid.uuid4().hex[:8]}"
        handle = arm.create(label)
        time.sleep(0.8)

        marker = f"SURV{uuid.uuid4().hex[:8].upper()}"
        arm.send(handle, f"(for n in 1 2 3 4 5 6 7 8; do echo {marker}_$n; sleep 1; done)")
        time.sleep(1.5)
        pre = arm.read(handle).count(marker)

        client_pid = arm.attach_client(handle, label)
        time.sleep(2.5)
        attached = client_pid is not None and arm.client_count(label) > 0
        on_target = arm.client_on_target(handle, label)

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

        time.sleep(7.0)
        server_up = arm.server_ready()
        out = arm.read(handle)
        completed = f"{marker}_8" in out

        emit({"metric": "survive", "arm": arm.name, "rep": i,
              "value": 1 if (completed and server_up) else 0,
              "valid": bool(attached and on_target and killed),
              "client_attached": attached, "client_on_target": on_target,
              "clients_killed": killed, "server_up_after": server_up,
              "pre_kill_retained": pre, "lines_retained": out.count(marker)})
        arm.close(handle)


def measure_server_start(arm, reps, emit):
    for i in range(reps):
        arm.server_stop()
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

    arms = [
        Herdr(),
        Tmux("tmux34", "3.4", TMUX34, "bench34"),
        Tmux("tmux37b", "3.7b", TMUX37B, "bench37b"),
    ]

    for arm in arms:
        emit({"metric": "arm_meta", "arm": arm.name, "version": arm.version,
              "binary": arm.binary})

    for arm in arms:
        arm.server_stop()
    time.sleep(2)
    for arm in arms:
        arm.server_start()
    time.sleep(4)
    for arm in arms:
        if not arm.server_ready():
            raise SystemExit(f"{arm.name} server did not start")

    # interleave arms per metric so host drift hits all three equally
    for fn, kwargs in (
        (measure_cli_overhead, {"reps": reps}),
        (measure_create, {"reps": reps}),
        (measure_roundtrip, {"reps": reps}),
        (measure_survival, {"reps": max(10, reps // 3)}),
    ):
        for arm in arms:
            print(f"  {fn.__name__} {arm.name}", flush=True)
            fn(arm, emit=emit, **kwargs)

    for arm in arms:
        print(f"  measure_scale {arm.name}", flush=True)
        measure_scale(arm, steps=[1, 5, 10, 20, 40], emit=emit)

    # 20 reps, not 8 — the site's own floor for a reported statistic
    for arm in arms:
        print(f"  measure_server_start {arm.name}", flush=True)
        measure_server_start(arm, reps=20, emit=emit)

    fh.close()
    print("BENCH_COMPLETE")


if __name__ == "__main__":
    main()
