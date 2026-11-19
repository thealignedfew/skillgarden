"""First-run helper: look for Claude Code account homes, then write a starter config and a rates file OUTSIDE the skill
folder. It never overwrites an existing file and never reads a credential.

    python init_config.py            show what it would write
    python init_config.py --write    write the config and the rates file, create the data folders

After it runs, open the files it names and check them: account labels and colours, the time zone, and above all the rates,
which are public list prices copied on the date in the file and go stale.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--timezone", default="UTC", help="IANA name such as America/New_York; UTC if you do not know")
    a = ap.parse_args(argv)
    homes = common.detect_homes()
    accts = [{"label": "default" if h.name == ".claude" else h.name.lstrip("."), "color": common.PALETTE[i % len(common.PALETTE)],
              "path": str(h).replace(str(Path.home()), "~", 1)} for i, h in enumerate(homes)]
    cfg = json.loads((SKILL / "config.example.json").read_text(encoding="utf-8"))
    cfg.pop("_comment", None)
    cfg["accounts"] = accts or cfg["accounts"]
    cfg["timezone"] = a.timezone
    cp, rp = common.config_path(), Path(common.DEFAULTS["rates_file"])
    common.say(f"account homes found: {len(homes)}" + ("" if homes else " (none; edit the accounts list by hand)"))
    for h in homes:
        common.say(f"  {h}")
    common.say(f"config file: {cp} ({'exists, will not overwrite' if cp.exists() else 'new'})")
    common.say(f"rates file : {rp} ({'exists, will not overwrite' if rp.exists() else 'new'})")
    if not a.write:
        common.say("dry run; add --write to create the new files")
        return 0
    cp.parent.mkdir(parents=True, exist_ok=True)
    if not cp.exists():
        cp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    rp.parent.mkdir(parents=True, exist_ok=True)
    if not rp.exists():
        shutil.copyfile(SKILL / "rates.example.json", rp)
    for d in (common.DEFAULTS["output_dir"], common.DEFAULTS["history_dir"]):
        Path(d).mkdir(parents=True, exist_ok=True)
    common.say("written. Check the rates against the public pricing page before trusting any dollar figure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
