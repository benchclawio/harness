from __future__ import annotations

import re
from typing import Any


FORBIDDEN_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "prompt",
    "raw_request",
    "raw_response",
    "secret",
    "session_id",
    "system_message",
    "token_value",
}

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|key)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'])/(?:home|Users|root|var|etc)/[^\s\"']+"),
]


def sanitize_message(message: str, maximum: int = 240) -> str:
    value = " ".join(str(message).split())
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value[:maximum]


def scan_public_value(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
                findings.append(f"{path}.{key}: forbidden key")
            findings.extend(scan_public_value(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(scan_public_value(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                findings.append(f"{path}: prohibited string pattern")
                break
    return findings
