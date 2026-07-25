#!/usr/bin/env python3
"""Read-only structural safety checks for a tar archive."""

from __future__ import annotations

import argparse
import json
import posixpath
import tarfile
from pathlib import PurePosixPath


def normalize(path: str) -> str:
    return posixpath.normpath(path)


def escapes_root(path: str) -> bool:
    normalized = normalize(path)
    return normalized == ".." or normalized.startswith("../") or normalized.startswith("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()

    counts: dict[str, int] = {}
    problems: list[dict[str, str]] = []

    with tarfile.open(args.archive, mode="r:*") as archive:
        for member in archive:
            kind = (
                "file"
                if member.isfile()
                else "directory"
                if member.isdir()
                else "symlink"
                if member.issym()
                else "hardlink"
                if member.islnk()
                else "other"
            )
            counts[kind] = counts.get(kind, 0) + 1

            if escapes_root(member.name):
                problems.append({"member": member.name, "problem": "member path escapes root"})

            if member.issym():
                target = normalize(
                    posixpath.join(str(PurePosixPath(member.name).parent), member.linkname)
                )
                if escapes_root(target):
                    problems.append(
                        {
                            "member": member.name,
                            "problem": f"symlink target escapes root: {member.linkname}",
                        }
                    )
            elif member.islnk() and escapes_root(member.linkname):
                problems.append(
                    {
                        "member": member.name,
                        "problem": f"hardlink target escapes root: {member.linkname}",
                    }
                )
            elif not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                problems.append(
                    {"member": member.name, "problem": f"unsupported member type: {member.type!r}"}
                )

    print(
        json.dumps(
            {
                "archive": args.archive,
                "counts": counts,
                "problems": problems,
                "safe": not problems,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
