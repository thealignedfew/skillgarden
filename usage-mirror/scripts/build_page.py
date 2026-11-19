"""Build the self-contained HTML page from usage_data.json and insights.json.

The template carries exactly one placeholder:  /*__USAGE_DATA__*/null
It is swapped for the JSON text. Every "<" in the JSON is written as \\u003c (valid inside JSON strings, and "<" can
only occur inside strings), so a session title containing "</script" or "<!--" cannot end or confuse the inline script.
The page makes no network request and loads no external file; it opens offline and can be published as a claude.ai
Artifact as it is.

Usage:  python build_page.py [--config FILE] [--data FILE] [--insights FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

HERE = Path(__file__).resolve().parent
PLACEHOLDER = "/*__USAGE_DATA__*/null"


def embed(data: dict) -> str:
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    text = text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if "</" in text:
        raise ValueError("escaping left a '</' sequence in the data")
    return text


def build(template: Path, data_path: Path, insights_path: Path | None, out_path: Path) -> dict:
    tpl = template.read_text(encoding="utf-8")
    n = tpl.count(PLACEHOLDER)
    if n != 1:
        raise ValueError(f"placeholder {PLACEHOLDER} found {n} times in {template} (expected exactly 1)")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    for key in ("generated_local", "sessions", "rows", "accounts"):
        if key not in data:
            raise ValueError(f"data is missing key '{key}': {data_path}")
    if insights_path and insights_path.is_file():
        ins = json.loads(insights_path.read_text(encoding="utf-8"))
        if not isinstance(ins, list):
            raise ValueError(f"insights file is not a list: {insights_path}")
        data["insights"] = ins
    html = tpl.replace(PLACEHOLDER, embed(data), 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return {"bytes": out_path.stat().st_size, "sessions": len(data["sessions"]), "rows": len(data["rows"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--data")
    ap.add_argument("--insights")
    ap.add_argument("--template", default=str(HERE / "page_template.html"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        cfg = common.load_config(a.config, require_accounts=False)
        out_dir = Path(cfg["output_dir"])
        data = Path(a.data) if a.data else out_dir / "usage_data.json"
        ins = Path(a.insights) if a.insights else Path(cfg["history_dir"]) / "insights.json"
        out = Path(a.out) if a.out else out_dir / "usage_mirror.html"
        if not data.is_file():
            common.die(f"data not found: {data}; run collect.py first")
        r = build(Path(a.template), data, ins, out)
    except (common.ConfigError, ValueError, json.JSONDecodeError) as e:
        common.die(str(e))
    common.say(f"BUILT {out} bytes={r['bytes']} sessions={r['sessions']} rows={r['rows']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
