"""Build a tiny synthetic Claude Code environment for tests: two account homes with transcripts, and a config.

Nothing here is real data. Timestamps are relative to `now` so the windows always contain them.
Transcript lines are compact JSON, the way Claude Code writes them (the collector matches on byte patterns).

    python make_fixture.py OUTDIR     writes OUTDIR/homes/acct-a, OUTDIR/homes/acct-b, OUTDIR/config.json, OUTDIR/rates.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

# sonnet-5 rates in rates.example.json: in 2, write_1h 4, write_5m 2.5, read 0.2, out 10 (US dollars per million tokens).
# This one response is 1,000,000 input + 500,000 1h-write + 2,000,000 read + 100,000 output = 2 + 2 + 0.4 + 1 = 5.4.
BIG = {"input_tokens": 1_000_000, "cache_creation_input_tokens": 500_000,
       "cache_creation": {"ephemeral_1h_input_tokens": 500_000, "ephemeral_5m_input_tokens": 0},
       "cache_read_input_tokens": 2_000_000, "output_tokens": 100_000}
BIG_USD = 5.4
SMALL = {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 10_000, "output_tokens": 500}
COLD = {"input_tokens": 10, "cache_creation_input_tokens": 60_000,
        "cache_creation": {"ephemeral_1h_input_tokens": 60_000, "ephemeral_5m_input_tokens": 0},
        "cache_read_input_tokens": 0, "output_tokens": 200}


def z(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def line(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":")) + "\n"


def user(uid, sid, t, text="please do the thing", **extra):
    return line({"type": "user", "uuid": uid, "sessionId": sid, "timestamp": z(t),
                 "message": {"role": "user", "content": text}, **extra})


def asst(mid, sid, t, usage, model="claude-sonnet-5", cwd="/work/proj-one"):
    return line({"type": "assistant", "uuid": "u-" + mid, "sessionId": sid, "timestamp": z(t), "cwd": cwd,
                 "message": {"id": mid, "model": model, "usage": usage}})


def make(out: Path, now: dt.datetime) -> dict:
    out = Path(out)
    ha, hb = out / "homes" / "acct-a", out / "homes" / "acct-b"
    pa, pb = ha / "projects" / "-work-proj-one", hb / "projects" / "-work-proj-two"
    (pa / "sess-a-0001" / "subagents").mkdir(parents=True, exist_ok=True)
    pb.mkdir(parents=True, exist_ok=True)
    m = lambda **kw: now - dt.timedelta(**kw)  # noqa: E731

    # session A1 in home A: typed turn, big response, a self-prompt turn, a peer turn, a cold rebuild, a compaction, a title
    a1 = "sess-a-0001"
    main_a = [
        line({"type": "custom-title", "customTitle": "Demo session one", "sessionId": a1}),
        user("ua-1", a1, m(hours=30)),
        asst("msg-a-1", a1, m(hours=30, minutes=-1), BIG),
        asst("msg-a-syn", a1, m(hours=30, minutes=-2), {"input_tokens": 5, "output_tokens": 5}, model="<synthetic>"),
        line({"type": "user", "uuid": "ua-tool", "sessionId": a1, "timestamp": z(m(hours=29, minutes=59)),
              "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "ok"}]}}),
        user("ua-2", a1, m(hours=5), "tick", turnOrigin="scheduled"),
        asst("msg-a-2", a1, m(hours=5, minutes=-1), SMALL),
        asst("msg-a-3", a1, m(hours=4), COLD),
        user("ua-3", a1, m(hours=3), "from another session", origin={"kind": "peer"}),
        asst("msg-a-4", a1, m(hours=3, minutes=-1), SMALL, model="claude-unknown-9"),
        line({"type": "system", "subtype": "compact_boundary", "uuid": "ua-cb", "sessionId": a1, "timestamp": z(m(hours=2)),
              "compactMetadata": {"preTokens": 150000, "trigger": "auto"}}),
        user("ua-4", a1, m(hours=1), "<command-name>/compact</command-name>"),
        user("ua-5", a1, m(minutes=30), "typed again"),
        asst("msg-a-5", a1, m(minutes=29), SMALL),
    ]
    (pa / (a1 + ".jsonl")).write_text("".join(main_a), encoding="utf-8")
    (pa / a1 / "subagents" / "agent-1.jsonl").write_text(
        asst("msg-a-sub", a1, m(hours=5, minutes=-2), SMALL), encoding="utf-8")

    # session B1 in home B, with a hostile title
    b1 = "sess-b-0001"
    main_b = [
        line({"type": "custom-title", "customTitle": "</script><b>hostile</b> & title", "sessionId": b1}),
        user("ub-1", b1, m(hours=2)),
        asst("msg-b-1", b1, m(hours=2, minutes=-1), BIG, cwd="/work/proj-two"),
        user("ub-2", b1, m(minutes=20), "typed"),
        asst("msg-b-2", b1, m(minutes=19), SMALL, cwd="/work/proj-two"),
    ]
    (pb / (b1 + ".jsonl")).write_text("".join(main_b), encoding="utf-8")

    # a copy of session A1 left in home B (a resume or an account move copies the transcript): same message ids
    copy = pb / (a1 + ".jsonl")
    copy.write_text("".join(main_a), encoding="utf-8")
    t_old, t_new = now.timestamp() - 7200, now.timestamp() - 3600
    os.utime(pa / (a1 + ".jsonl"), (t_old, t_old))   # the original was written first, so ties go to home A
    os.utime(copy, (t_new, t_new))

    rates = SKILL / "rates.example.json"
    cfg = {"accounts": [{"label": "acct-a", "color": "#2a78d6", "path": str(ha)},
                        {"label": "acct-b", "color": "#eb6834", "path": str(hb)}],
           "output_dir": str(out / "out"), "history_dir": str(out / "history"), "rates_file": str(rates),
           "timezone": "UTC", "days": 45, "scan_days": 60, "live_meters": False, "live_reuse_seconds": 0,
           "user_agent": "usage-mirror-test"}
    (out / "config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return cfg


if __name__ == "__main__":
    make(Path(sys.argv[1]), dt.datetime.now(dt.timezone.utc))
    print("fixture written to", sys.argv[1])
