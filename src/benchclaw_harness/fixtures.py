from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _number(seed_material: str, modulus: int) -> int:
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulus


def _metrics(seed_material: str, completed: bool) -> dict[str, Any]:
    base = _number(seed_material, 17)
    return {
        "tokens_in": 80 + base,
        "tokens_out": (28 + base) if completed else (12 + base),
        "cost_usd": 0.0,
        "wall_time_s": round(0.08 + base / 1000, 4),
        "tool_calls": 2 + (base % 3),
    }


def fixture_stable(task: dict[str, Any], seed_material: str) -> dict[str, Any]:
    return {
        "status": "success",
        "completed": True,
        "metrics": _metrics(seed_material, True),
        "failure": None,
    }


def fixture_variable(task: dict[str, Any], seed_material: str) -> dict[str, Any]:
    roll = _number(seed_material, 10)
    completed = roll not in {0, 1, 2}
    if completed:
        return {
            "status": "success",
            "completed": True,
            "metrics": _metrics(seed_material, True),
            "failure": None,
        }
    failure_type = "tool_error" if roll == 0 else "invalid_final_answer"
    return {
        "status": "failure",
        "completed": False,
        "metrics": _metrics(seed_material, False),
        "failure": {
            "type": failure_type,
            "stage": "fixture_execution",
            "message_sanitized": "Deterministic fixture failure.",
        },
    }


# ---------------------------------------------------------------------------
# Real-framework subprocess worker adapters
# ---------------------------------------------------------------------------

_ADAPTERS_DIR = Path(__file__).parent.parent.parent / "adapters"
_VENVS_DIR = Path(__file__).parent.parent.parent / ".venvs"
_CREDENTIALS_DIR = Path.home() / ".openclaw" / "credentials"

_WORKER_ENV_BASE = {
    "PATH": str(_VENVS_DIR / "langgraph" / "bin") + ":/usr/bin:/bin",
    "HOME": str(Path.home()),
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_API_KEY": "",
    "LANGSMITH_API_KEY": "",
    "LOGFIRE_SEND_TO_LOGFIRE": "false",
    "LOGFIRE_TOKEN": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
}


def _read_credential(name: str) -> str:
    """Read a credential from the approved store; raise if absent or empty."""
    path = _CREDENTIALS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"credential not found: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"credential is empty: {path}")
    return value


def _make_worker_adapter(python_exe: Path, worker_script: Path, fake_mode: str = "correct"):
    """Return an adapter callable that spawns a framework subprocess worker (fake mode)."""
    python_str = str(python_exe)
    script_str = str(worker_script)
    env = {**_WORKER_ENV_BASE, "PATH": str(python_exe.parent) + ":/usr/bin:/bin"}

    def adapter(task: dict[str, Any], seed_material: str) -> dict[str, Any]:
        request = json.dumps({"task": task, "mode": "fake", "fake_mode": fake_mode})
        try:
            proc = subprocess.run(
                [python_str, script_str],
                input=request,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            if not proc.stdout.strip():
                raise RuntimeError(
                    f"worker produced no output (exit={proc.returncode}): {proc.stderr[:200]}"
                )
            result = json.loads(proc.stdout.strip())
        except Exception as exc:
            result = {
                "status": "error",
                "completed": False,
                "metrics": {
                    "tokens_in": None,
                    "tokens_out": None,
                    "cost_usd": 0.0,
                    "wall_time_s": None,
                    "tool_calls": None,
                },
                "failure": {
                    "type": "adapter_install_error",
                    "stage": "adapter",
                    "message_sanitized": type(exc).__name__[:240],
                },
            }
        # Strip extra keys (score, etc.) that the harness doesn't expect
        return {k: result[k] for k in ("status", "completed", "metrics", "failure") if k in result}

    return adapter


def _make_live_worker_adapter(
    python_exe: Path,
    worker_script: Path,
    model_id: str = "gpt-4o-mini",
    credential_name: str = "openai-api-key",
):
    """Return an adapter callable that spawns a framework subprocess worker (live mode).

    Reads the OpenAI API key from the approved credential store at call time.
    Each invocation requires a fresh allow-once approval per standing policy.
    """
    python_str = str(python_exe)
    script_str = str(worker_script)
    base_env = {**_WORKER_ENV_BASE, "PATH": str(python_exe.parent) + ":/usr/bin:/bin"}

    def adapter(task: dict[str, Any], seed_material: str) -> dict[str, Any]:
        try:
            api_key = _read_credential(credential_name)
        except (FileNotFoundError, ValueError) as exc:
            return {
                "status": "error",
                "completed": False,
                "metrics": {
                    "tokens_in": None,
                    "tokens_out": None,
                    "cost_usd": 0.0,
                    "wall_time_s": None,
                    "tool_calls": None,
                },
                "failure": {
                    "type": "authentication_error",
                    "stage": "adapter",
                    "message_sanitized": type(exc).__name__[:240],
                },
            }

        env = {**base_env, "OPENAI_API_KEY": api_key}
        request = json.dumps({"task": task, "mode": "live", "model_id": model_id})
        try:
            proc = subprocess.run(
                [python_str, script_str],
                input=request,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if not proc.stdout.strip():
                raise RuntimeError(
                    f"worker produced no output (exit={proc.returncode}): {proc.stderr[:200]}"
                )
            result = json.loads(proc.stdout.strip())
        except Exception as exc:
            result = {
                "status": "error",
                "completed": False,
                "metrics": {
                    "tokens_in": None,
                    "tokens_out": None,
                    "cost_usd": 0.0,
                    "wall_time_s": None,
                    "tool_calls": None,
                },
                "failure": {
                    "type": "adapter_install_error",
                    "stage": "adapter",
                    "message_sanitized": type(exc).__name__[:240],
                },
            }
        return {k: result[k] for k in ("status", "completed", "metrics", "failure") if k in result}

    return adapter


ADAPTERS: dict[str, Any] = {
    "fixture_stable": fixture_stable,
    "fixture_variable": fixture_variable,
    "langgraph_1_2_9": _make_worker_adapter(
        _VENVS_DIR / "langgraph" / "bin" / "python",
        _ADAPTERS_DIR / "worker_langgraph.py",
    ),
    "pydantic_ai_2_13_0": _make_worker_adapter(
        _VENVS_DIR / "pydantic-ai" / "bin" / "python",
        _ADAPTERS_DIR / "worker_pydantic_ai.py",
    ),
    "langgraph_1_2_9_live": _make_live_worker_adapter(
        _VENVS_DIR / "langgraph" / "bin" / "python",
        _ADAPTERS_DIR / "worker_langgraph.py",
    ),
    "pydantic_ai_2_13_0_live": _make_live_worker_adapter(
        _VENVS_DIR / "pydantic-ai" / "bin" / "python",
        _ADAPTERS_DIR / "worker_pydantic_ai.py",
    ),
    # gpt-4o live variants (publication-eligible pilot)
    "langgraph_1_2_9_gpt4o_live": _make_live_worker_adapter(
        _VENVS_DIR / "langgraph" / "bin" / "python",
        _ADAPTERS_DIR / "worker_langgraph.py",
        model_id="gpt-4o",
    ),
    "pydantic_ai_2_13_0_gpt4o_live": _make_live_worker_adapter(
        _VENVS_DIR / "pydantic-ai" / "bin" / "python",
        _ADAPTERS_DIR / "worker_pydantic_ai.py",
        model_id="gpt-4o",
    ),
}
