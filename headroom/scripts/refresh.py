"""One refresh of Headroom: read the plan meters, read new transcript bytes, rebuild the data and the page.

    python refresh.py                  full refresh (meters live if the config says so)
    python refresh.py --no-live        skip the usage endpoint; use stored readings only
    python refresh.py --outliers       also write a new outliers review run (default window 12 hours)
    python refresh.py --fixture FILE   read synthetic meter payloads from FILE instead of the endpoint (testing)

Both the scan and the meter read are incremental and cheap, so a normal refresh takes seconds to a minute. The only
network call is the usage endpoint, one request per account at most, and only when live_meters is true.
Prints one line per step and ends with the page path. Exit code is non-zero if a required step fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_page  # noqa: E402
import collect  # noqa: E402
import common  # noqa: E402
import meters  # noqa: E402
import outliers  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--no-live", action="store_true")
    ap.add_argument("--fixture")
    ap.add_argument("--outliers", action="store_true")
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--days", type=int)
    a = ap.parse_args(argv)
    try:
        cfg = common.load_config(a.config)
    except common.ConfigError as e:
        common.die(str(e))
    if a.days:
        cfg["days"] = a.days
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(cfg["history_dir"]).mkdir(parents=True, exist_ok=True)

    live = bool(cfg["live_meters"]) and not a.no_live
    fx = json.loads(Path(a.fixture).read_text(encoding="utf-8")) if a.fixture else None
    if live or fx is not None:
        m = meters.read_all(cfg, live=live, fixture=fx)
        n = meters.append_history(cfg["history_dir"], m)
        for label, r in m.items():
            common.say("meters " + meters._summary(label, r))
        common.say(f"meters history rows added: {n}")
    else:
        common.say("meters skipped (live off); stored readings are used")

    st = collect.scan(cfg)
    common.say("collect " + json.dumps({k: v for k, v in st.items() if k != "missing_homes"}))
    if st["missing_homes"]:
        common.say("NOTE no projects folder for: " + ", ".join(st["missing_homes"]) + " (check the path in the config)")

    data = collect.build(cfg)
    dp = out_dir / "usage_data.json"
    dp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    common.say(f"data sessions={len(data['sessions'])} rows={len(data['rows'])}")

    if a.outliers:
        run = outliers.compute(cfg, a.hours)
        outliers.append_run(cfg["history_dir"], run)
        common.say(f"outliers {len(run['items'])} items, window {run['window_from']} to {run['window_to']}")

    try:
        r = build_page.build(Path(__file__).resolve().parent / "page_template.html", dp,
                             Path(cfg["history_dir"]) / "insights.json", out_dir / "headroom.html")
    except (ValueError, json.JSONDecodeError) as e:
        common.die(str(e))
    common.say(f"page {out_dir / 'headroom.html'} bytes={r['bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
