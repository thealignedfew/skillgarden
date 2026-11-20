"""Leak scan: refuse to publish a folder that carries private material.

    python leak_scan.py [ROOT] [--terms FILE]

ROOT defaults to the skill folder. It scans every text file under it. Exit code 0 with "PASS" when there is no hit,
1 with "FAIL" and one line per hit, file:line, rule, a short masked excerpt.

Two rule sets:
  * Built in, generic: email addresses, drive-letter and home-folder paths, UUIDs, claude.ai artifact links, token and key
    shapes, em and en dashes, and in Markdown and JSON files a dollar amount or a percentage (outside fenced code blocks) that is not marked as an
    example on its line (words such as example, synthetic, fixture, illustration, e.g.).
  * Owner terms, optional: a JSON file of private names, seat names, account names and real figures the owner never
    wants published. They are kept OUT of the skill folder so the public package does not list them. Looked for in this
    order: --terms, the HEADROOM_LEAK_TERMS environment variable (the old name USAGE_MIRROR_LEAK_TERMS is still read),
    ROOT/../_owner_only/leak_terms.json.
    Format: {"terms": [{"name": "label", "pattern": "regex", "flags": "i", "allow": "regex that clears a line"}]}

Run it before every push. A person forking the skill should run it with their own terms file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git", "_work", "node_modules"}
TEXT_EXT = {".md", ".py", ".json", ".html", ".txt", ".js", ".css", ".toml", ".yml", ".yaml", ".cfg", ".ini", ""}
EXAMPLE_WORDS = re.compile(r"example|synthetic|fixture|illustrat|e\.g\.|for instance|suppose|sample|placeholder", re.I)

# built in rules: (name, regex, applies-to extensions or None for all, masks the excerpt)
_T = "sk" + "-ant-"
RULES = [
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", None, False),
    ("drive-path", r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", None, False),
    ("home-path", r"(?:/Users/|/home/)[A-Za-z0-9._-]+", None, False),
    ("uuid", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", None, False),
    ("artifact-link", r"claude\.ai/(?:code/)?artifact/", None, False),
    ("token-anthropic", _T + r"[A-Za-z0-9_-]{8,}", None, True),
    ("token-github", r"\bgh[pousr]_[A-Za-z0-9]{20,}", None, True),
    ("token-aws", r"\bAKIA[0-9A-Z]{16}\b", None, True),
    ("token-jwt", r"\beyJ[A-Za-z0-9_-]{20,}\.", None, True),
    ("token-bearer", r"Bearer\s+[A-Za-z0-9._~+/-]{20,}", None, True),
    ("secret-assignment", r"(?i)(?:api[_-]?key|secret|token|password)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+_-]{16,}[\"']", None, True),
    ("long-hex", r"\b[0-9a-f]{40,}\b", None, True),
    ("em-dash", "\u2014", None, False),
    ("en-dash", "\u2013", None, False),
    ("dollar-figure", r"\$\d{3,}|\$\d[\d,]*\.\d\d\b", {".md", ".json"}, False),
    ("percent-figure", r"\b\d{1,3}(?:\.\d+)?%", {".md"}, False),
]


def load_terms(path: Path | None) -> tuple[list, str]:
    if path is None:
        return [], "none"
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for t in data.get("terms", []):
        fl = re.I if "i" in (t.get("flags") or "") else 0
        out.append((t["name"], re.compile(t["pattern"], fl), re.compile(t["allow"]) if t.get("allow") else None))
    return out, str(path)


def iter_files(root: Path):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            p = Path(dirpath) / fn
            if p.suffix.lower() in TEXT_EXT:
                yield p


def mask(s: str) -> str:
    return s[:6] + "..." if len(s) > 6 else "..."


def scan(root: Path, terms: list) -> tuple[list, int]:
    hits = []
    nfiles = 0
    builtin = [(n, re.compile(rx), ext, mk) for n, rx, ext, mk in RULES]
    for p in iter_files(root):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        nfiles += 1
        text = raw.decode("utf-8", "replace")
        rel = p.relative_to(root).as_posix()
        in_fence = False
        for ln, line in enumerate(text.splitlines(), 1):
            if p.suffix.lower() == ".md" and line.lstrip().startswith("```"):
                in_fence = not in_fence
            for name, rx, ext, mk in builtin:
                if ext is not None and p.suffix.lower() not in ext:
                    continue
                if name in ("dollar-figure", "percent-figure") and EXAMPLE_WORDS.search(line):
                    continue
                if name == "percent-figure" and in_fence:
                    continue  # command output in a fenced block; the owner terms still apply there
                m = rx.search(line)
                if m:
                    hits.append((rel, ln, name, mask(m.group(0)) if mk else m.group(0)[:40]))
            for name, rx, allow in terms:
                for m in rx.finditer(line):
                    if allow and allow.search(line):
                        break
                    hits.append((rel, ln, "term:" + name, m.group(0)[:40]))
                    break
    return hits, nfiles


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--terms")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    tp = a.terms or os.environ.get("HEADROOM_LEAK_TERMS") or os.environ.get("USAGE_MIRROR_LEAK_TERMS")
    tpath = Path(tp) if tp else (root.parent / "_owner_only" / "leak_terms.json")
    try:
        terms, used = load_terms(tpath if tpath.is_file() else None)
    except (ValueError, KeyError, re.error) as e:
        print(f"FAIL terms file unusable: {e}", file=sys.stderr)
        return 2
    hits, n = scan(root, terms)
    for rel, ln, name, ex in hits:
        print(f"HIT {rel}:{ln}: [{name}] {ex}")
    if hits:
        print(f"FAIL {len(hits)} hits in {n} files (owner terms: {used})")
        return 1
    print(f"PASS 0 hits in {n} files (owner terms: {used})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
