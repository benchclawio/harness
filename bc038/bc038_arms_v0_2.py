#!/usr/bin/env python3
"""bc-038 v0.2.0 runner wrapper.

The preserved v0.1 runner contains the framework adapters. This wrapper pins an immutable
judge snapshot and makes the local usage ledger a blocking dependency. The ledger proxy
also enforces the model and temperature on requests made inside framework SDKs.
"""

from __future__ import annotations

import json
import os
import urllib.request

import bc038_arms as runner


JUDGE_MODEL = "gpt-4o-2024-08-06"
runner.JUDGE_MODEL = JUDGE_MODEL

original_render = runner.render


def render_with_context(case: dict) -> str:
    context_url = os.environ.get("BC038_LEDGER_CONTEXT_URL")
    if not context_url:
        raise RuntimeError("BC038_LEDGER_CONTEXT_URL is required; usage cannot be unmeasured")
    case_id = case.get("case_id")
    if case_id is None:
        available = case.get("agent_output", {}).get("available")
        case_id = "positive-control-correct" if available == 41 else "positive-control-wrong"
    body = json.dumps({"context": case_id}).encode()
    request = urllib.request.Request(
        context_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"ledger context rejected with status {response.status}")
    return original_render(case)


runner.render = render_with_context


if __name__ == "__main__":
    runner.main()
