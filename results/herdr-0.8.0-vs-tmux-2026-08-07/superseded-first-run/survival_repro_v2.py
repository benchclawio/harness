#!/usr/bin/env python3
"""
bc-044 — survival reproduction, corrected scoping (v2).

v1 (and the scored run it came from) attached the Herdr client with a bare
`herdr`, which attaches to the *focused* workspace. Every rep created a fresh
workspace but never focused it, so the client under test was rendering a
different workspace than the one running the marker loop. The tmux arm, by
contrast, used `tmux attach-session -t <label>` — attached directly to the
session under test. The two arms were not running the same experiment, and the
Herdr arm was running the easier one.

v2 focuses the workspace before attaching, verifies from the server snapshot
that the client is actually on the workspace under test, and records that as a
per-rep validity gate. A rep that cannot be shown to have had a client attached
to the pane under test is recorded invalid rather than as a pass.

Usage: python3 bc044_survival_repro_v2.py <out.jsonl> <reps> <arm>
"""
import json
import os
import subprocess
import sys
import time
import uuid

HERDR = os.path.expanduser("~/.local/bin/herdr")


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def herdr_ready():
    r = run([HERDR, "status", "server"], timeout=10)
    for line in r.stdout.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip() == "running"
    return False


def focused_workspace():
    """Which workspace the server currently considers focused."""
    r = run([HERDR, "api", "snapshot"], timeout=15)
    try:
        return json.loads(r.stdout)["result"]["snapshot"]["focused_workspace_id"]
    except Exception:
        return None


def herdr_client_procs():
    """Extra herdr processes beyond the single headless server."""
    r = run(["pgrep", "-x", "herdr"])
    return max(0, len([p for p in r.stdout.split() if p.strip()]) - 1)


def main():
    out_path, reps, arm = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    fh = open(out_path, "a", buffering=1)

    for i in range(reps):
        label = f"rv{uuid.uuid4().hex[:8]}"
        rec = {"rep": i, "arm": arm, "label": label, "ts": time.time(),
               "scoping": "v2-focused"}

        if arm == "herdr":
            r = run([HERDR, "workspace", "create", "--label", label, "--cwd", "/root"])
            handle = json.loads(r.stdout)["result"]["root_pane"]["pane_id"]
            ws_id = handle.split(":")[0]
            rec["workspace_id"] = ws_id
            # the correction: put the workspace under test in front of the client
            run([HERDR, "workspace", "focus", ws_id])
            rec["focused_before_attach"] = focused_workspace()
        else:
            run(["tmux", "new-session", "-d", "-s", label, "-c", "/root"])
            handle = label
        rec["handle"] = handle
        time.sleep(0.8)

        marker = f"SURV{uuid.uuid4().hex[:8].upper()}"
        rec["marker"] = marker
        cmd = f"(for n in 1 2 3 4 5 6 7 8; do echo {marker}_$n; sleep 1; done)"
        if arm == "herdr":
            run([HERDR, "pane", "send-text", handle, cmd])
            run([HERDR, "pane", "send-keys", handle, "Enter"])
        else:
            run(["tmux", "send-keys", "-t", handle, cmd, "Enter"])
        time.sleep(1.5)

        if arm == "herdr":
            pre = run([HERDR, "pane", "read", handle]).stdout
        else:
            pre = run(["tmux", "capture-pane", "-p", "-t", handle]).stdout
        rec["pre_kill_retained"] = pre.count(marker)

        if arm == "herdr":
            client = subprocess.Popen(
                ["script", "-q", "-c", HERDR, "/dev/null"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
                env={**os.environ, "TERM": "xterm-256color"})
        else:
            client = subprocess.Popen(
                ["script", "-q", "-c", f"tmux attach-session -t {label}", "/dev/null"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
                env={**os.environ, "TERM": "xterm-256color"})
        time.sleep(2.5)

        # validity: a client is really attached, and it is really on this work
        if arm == "herdr":
            rec["client_procs"] = herdr_client_procs()
            rec["focused_at_attach"] = focused_workspace()
            rec["client_attached"] = rec["client_procs"] > 0
            rec["client_on_target"] = rec["focused_at_attach"] == rec["workspace_id"]
        else:
            clients = run(["tmux", "list-clients", "-t", label]).stdout
            rec["client_procs"] = len([l for l in clients.splitlines() if l.strip()])
            rec["client_attached"] = rec["client_procs"] > 0
            rec["client_on_target"] = rec["client_attached"]

        try:
            os.killpg(os.getpgid(client.pid), 9)
            rec["killed"] = True
        except (ProcessLookupError, PermissionError):
            rec["killed"] = False

        time.sleep(7.0)

        if arm == "herdr":
            rr = run([HERDR, "pane", "read", handle])
            rec["server_up_after"] = herdr_ready()
            panes = run([HERDR, "pane", "list"]).stdout
            rec["pane_still_listed"] = handle in panes
        else:
            rr = run(["tmux", "capture-pane", "-p", "-t", handle])
            rec["server_up_after"] = run(["tmux", "list-sessions"]).returncode == 0
            rec["pane_still_listed"] = label in run(["tmux", "list-sessions"]).stdout

        out = rr.stdout
        rec["read_rc"] = rr.returncode
        rec["post_kill_retained"] = out.count(marker)
        rec["completed"] = f"{marker}_8" in out
        rec["valid"] = bool(rec["client_attached"] and rec["client_on_target"]
                            and rec["killed"])
        rec["ok"] = bool(rec["completed"] and rec["server_up_after"])
        if not rec["ok"] or not rec["valid"]:
            rec["read_stdout"] = out[-1500:]
            rec["read_stderr"] = rr.stderr[-800:]

        fh.write(json.dumps(rec) + "\n")
        print(f"{arm} rep{i} ok={rec['ok']} valid={rec['valid']} "
              f"pre={rec['pre_kill_retained']} post={rec['post_kill_retained']} "
              f"on_target={rec['client_on_target']} listed={rec['pane_still_listed']}",
              flush=True)

        if arm == "herdr":
            run([HERDR, "pane", "close", handle])
        else:
            run(["tmux", "kill-session", "-t", handle])

    fh.close()
    print("REPRO_COMPLETE")


if __name__ == "__main__":
    main()
