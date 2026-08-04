"""Measure the progressive-disclosure ratio of real SKILL.md files.

Every ranking page for "what is a claude skill" asserts that progressive disclosure
saves context, and none publishes a figure. A token count needs a tokenizer we do not
have offline, and an estimated token count is not a measurement.

What IS exactly measurable, with no model call and no tokenizer: the proportion of a
Skill that is always loaded (YAML frontmatter: name + description) versus the
proportion that stays on disk until the Skill is triggered.

Usage:
    python3 measure_skill_disclosure.py <skills-dir> [<skills-dir> ...]
"""

import os
import sys


def split_frontmatter(text):
    """Return (frontmatter, body). Frontmatter is the leading --- ... --- block."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    return text[: end + 4], text[end + 4:]


def parse_scalar(frontmatter, key):
    """Pull a top-level `key: value` out of the frontmatter without a YAML dep."""
    for line in frontmatter.splitlines():
        if line.startswith(key + ":"):
            return line[len(key) + 1:].strip().strip('"').strip("'")
    return ""


def measure(skill_dir):
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    frontmatter, body = split_frontmatter(text)
    name = parse_scalar(frontmatter, "name") or os.path.basename(skill_dir)
    description = parse_scalar(frontmatter, "description")

    # Always-loaded surface = what the model sees at startup: name + description.
    always = len(name) + len(description)

    # Everything bundled with the Skill, not just SKILL.md.
    bundled = 0
    for root, _dirs, files in os.walk(skill_dir):
        for filename in files:
            try:
                bundled += os.path.getsize(os.path.join(root, filename))
            except OSError:
                pass

    return {
        "name": name,
        "always_bytes": always,
        "skill_md_bytes": len(text),
        "bundled_bytes": bundled,
        "pct_of_skill_md": 100.0 * always / len(text) if text else 0.0,
        "pct_of_bundle": 100.0 * always / bundled if bundled else 0.0,
    }


def main():
    roots = sys.argv[1:]
    if not roots:
        print(__doc__)
        return 2

    rows = []
    for root in roots:
        for entry in sorted(os.listdir(root)):
            result = measure(os.path.join(root, entry))
            if result:
                rows.append(result)

    if not rows:
        print("no SKILL.md files found")
        return 1

    rows.sort(key=lambda r: r["bundled_bytes"], reverse=True)

    print(f"{'skill':<34}{'always':>8}{'SKILL.md':>10}{'bundle':>10}"
          f"{'% md':>8}{'% bundle':>10}")
    print("-" * 80)
    for row in rows:
        print(f"{row['name'][:33]:<34}{row['always_bytes']:>8}"
              f"{row['skill_md_bytes']:>10}{row['bundled_bytes']:>10}"
              f"{row['pct_of_skill_md']:>7.1f}%{row['pct_of_bundle']:>9.2f}%")

    total_always = sum(r["always_bytes"] for r in rows)
    total_md = sum(r["skill_md_bytes"] for r in rows)
    total_bundle = sum(r["bundled_bytes"] for r in rows)
    median_md = sorted(r["pct_of_skill_md"] for r in rows)[len(rows) // 2]
    median_bundle = sorted(r["pct_of_bundle"] for r in rows)[len(rows) // 2]

    print("-" * 80)
    print(f"skills measured           : {len(rows)}")
    print(f"always-loaded total       : {total_always:,} bytes")
    print(f"SKILL.md total            : {total_md:,} bytes")
    print(f"bundled total             : {total_bundle:,} bytes")
    print(f"always-loaded share of md : {100.0 * total_always / total_md:.2f}%")
    print(f"always-loaded share of all: {100.0 * total_always / total_bundle:.2f}%")
    print(f"median share of md        : {median_md:.2f}%")
    print(f"median share of bundle    : {median_bundle:.2f}%")
    print(f"deferred until triggered  : {100.0 - 100.0 * total_always / total_bundle:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
