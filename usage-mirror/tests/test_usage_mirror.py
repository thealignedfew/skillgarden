"""Tests for usage-mirror. Standard library only. Run from the skill folder:

    python -m unittest discover -s tests -v

Every input is synthetic. The real usage endpoint is never called: the live reader is tested with a patched urlopen and a
fake credentials file, and the rest of the meter path with fixture payloads.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(HERE))

import build_page  # noqa: E402
import collect  # noqa: E402
import common  # noqa: E402
import leak_scan  # noqa: E402
import make_fixture  # noqa: E402
import meters  # noqa: E402
import outliers  # noqa: E402

NOW = dt.datetime(2026, 11, 19, 15, 0, tzinfo=dt.timezone.utc)


def payload(reset5: dt.datetime, reset7: dt.datetime, five: float = 75, seven: float = 40) -> dict:
    text = (HERE / "fixture" / "usage_payload_example.json").read_text(encoding="utf-8")
    text = text.replace("__RESET_5H__", reset5.isoformat()).replace("__RESET_7D__", reset7.isoformat())
    d = json.loads(text)
    d["acct-a"]["five_hour"]["utilization"] = five
    d["acct-a"]["seven_day"]["utilization"] = seven
    d.pop("_comment", None)
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="um-test-"))
        self.cfg_raw = make_fixture.make(self.tmp, NOW)
        self.cfg = common.load_config(self.tmp / "config.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ConfigTests(Base):
    def test_load_and_expand(self):
        self.assertEqual([a["label"] for a in self.cfg["accounts"]], ["acct-a", "acct-b"])
        self.assertTrue(isinstance(self.cfg["output_dir"], Path))

    def test_env_override_and_defaults(self):
        with mock.patch.dict(os.environ, {"USAGE_MIRROR_CONFIG": str(self.tmp / "config.json")}):
            self.assertEqual(common.config_path(), self.tmp / "config.json")
            self.assertEqual(common.load_config()["days"], 45)

    def test_duplicate_label_is_refused(self):
        raw = dict(self.cfg_raw)
        raw["accounts"] = [raw["accounts"][0], raw["accounts"][0]]
        (self.tmp / "dup.json").write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(common.ConfigError):
            common.load_config(self.tmp / "dup.json")

    def test_bad_json_is_refused(self):
        (self.tmp / "bad.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(common.ConfigError):
            common.load_config(self.tmp / "bad.json")

    def test_unknown_timezone_falls_back_loudly(self):
        c = common.Clock("Nowhere/Land")
        self.assertEqual(c.effective, "UTC")
        self.assertIn("could not be loaded", c.warning)

    def test_example_files_parse(self):
        json.loads((SKILL / "config.example.json").read_text(encoding="utf-8"))
        tbl, ver, prob = common.load_rates(SKILL / "rates.example.json")
        self.assertEqual(prob, "")
        self.assertIn("claude-sonnet-5", tbl)
        self.assertEqual(common.rate_for("claude-sonnet-5-20260101", tbl), tbl["claude-sonnet-5"])
        self.assertEqual(common.rate_for("claude-fable-5-1", tbl)["read"], 0.25)
        self.assertIsNone(common.rate_for("claude-unknown-9", tbl))


class CollectTests(Base):
    def test_scan_is_incremental_and_dedupes(self):
        st = collect.scan(self.cfg)
        self.assertEqual(st["missing_homes"], [])
        import sqlite3
        con = sqlite3.connect(collect.db_path(self.cfg))
        n_calls = con.execute("select count(*) from calls").fetchone()[0]
        self.assertEqual(n_calls, 8)  # 6 in session A (copy in home B not double counted, synthetic skipped), 2 in session B
        n_turns = con.execute("select count(*) from turns where origin != 'command'").fetchone()[0]
        self.assertEqual(n_turns, 4 + 1 + 1)  # typed 4, scheduled 1, peer 1
        con.close()
        st2 = collect.scan(self.cfg)
        self.assertEqual(st2["files_read"], 0)  # nothing new, nothing read
        con = sqlite3.connect(collect.db_path(self.cfg))
        self.assertEqual(con.execute("select count(*) from calls").fetchone()[0], 8)
        con.close()

    def test_partial_line_is_picked_up_later(self):
        p = self.tmp / "homes" / "acct-b" / "projects" / "-work-proj-two" / "sess-b-0001.jsonl"
        collect.scan(self.cfg)
        full = make_fixture.asst("msg-b-late", "sess-b-0001", NOW, make_fixture.SMALL, cwd="/work/proj-two")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(full[:40])           # a line still being written, no newline
        collect.scan(self.cfg)
        import sqlite3
        con = sqlite3.connect(collect.db_path(self.cfg))
        self.assertEqual(con.execute("select count(*) from calls where msg_id='msg-b-late'").fetchone()[0], 0)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(full[40:])
        con.close()
        collect.scan(self.cfg)
        con = sqlite3.connect(collect.db_path(self.cfg))
        self.assertEqual(con.execute("select count(*) from calls where msg_id='msg-b-late'").fetchone()[0], 1)
        con.close()

    def test_build_numbers(self):
        collect.scan(self.cfg)
        d = collect.build(self.cfg, now_utc=NOW)
        R = {c: i for i, c in enumerate(d["row_cols"])}
        usd = sum(r[R["usd"]] for r in d["rows"])
        self.assertAlmostEqual(usd, 5.4 + 5.4 + 0.009 * 4 + 0.24202, places=4)
        self.assertEqual(sum(r[R["calls"]] for r in d["rows"]), 8)
        # the moved copy belongs to account A, the account whose file stopped growing first
        a_calls = sum(r[R["calls"]] for r in d["rows"] if r[R["account"]] == 0)
        self.assertEqual(a_calls, 6)
        self.assertEqual(d["unpriced_models"], {"claude-unknown-9": 1})
        TR = {c: i for i, c in enumerate(d["turn_row_cols"])}
        self.assertEqual(sum(t[TR["typed"]] for t in d["turn_rows"]), 4)
        self.assertEqual(sum(t[TR["scheduled"]] for t in d["turn_rows"]), 1)
        self.assertEqual(sum(t[TR["peer"]] for t in d["turn_rows"]), 1)
        self.assertEqual(len(d["compactions"]), 1)
        self.assertEqual(len(d["cache_rebuilds"]), 1)
        self.assertAlmostEqual(d["cache_rebuilds"][0][3], 0.228, places=4)
        titles = [s[1] for s in d["sessions"]]
        self.assertIn("Demo session one", titles)
        self.assertEqual(d["timezone_effective"], "UTC")

    def test_no_message_text_is_stored(self):
        collect.scan(self.cfg)
        raw = collect.db_path(self.cfg).read_bytes()
        self.assertNotIn(b"please do the thing", raw)
        self.assertNotIn(b"typed again", raw)

    def test_missing_rates_turn_dollars_off_not_crash(self):
        collect.scan(self.cfg)
        self.cfg["rates_file"] = self.tmp / "nope.json"
        d = collect.build(self.cfg, now_utc=NOW)
        self.assertIn("not found", d["rates_problem"])
        R = {c: i for i, c in enumerate(d["row_cols"])}
        self.assertEqual(sum(r[R["usd"]] for r in d["rows"]), 0)


class MeterTests(Base):
    def test_normalize_fixture(self):
        d = payload(NOW + dt.timedelta(hours=4), NOW + dt.timedelta(days=3))
        n = meters.normalize(d["acct-a"])
        self.assertEqual(n["five_hour"]["pct"], 75)
        self.assertEqual([s["key"] for s in n["scoped"]], ["opus"])
        self.assertEqual(len(n["limits"]), 2)
        self.assertEqual(n["limits"][0]["severity"], "critical")
        self.assertEqual(n["limits"][1]["label"], "Example Model")
        ex = n["extra_usage"]
        self.assertAlmostEqual(ex["used"], 12.5)
        self.assertAlmostEqual(ex["monthly_limit"], 500.0)
        self.assertIsNone(meters.normalize(d["acct-b"])["extra_usage"])

    def test_normalize_tolerates_unknown_shapes(self):
        n = meters.normalize({"five_hour": "weird", "limits": ["x", {"foo": 1}], "extra_usage": {"is_enabled": False}})
        self.assertIsNone(n["five_hour"])
        self.assertEqual(len(n["limits"]), 1)
        self.assertIsNone(n["extra_usage"]["used"])

    def test_forecast_example_from_the_whitepaper(self):
        t0 = NOW
        t1 = NOW + dt.timedelta(minutes=50)
        rows = [{"account": "x", "at": t0.isoformat(), "five_hour": 75.0}, {"account": "x", "at": t1.isoformat(), "five_hour": 81.0}]
        f = meters.forecast(rows, "five_hour", (t1 + dt.timedelta(hours=4)).isoformat(), now=t1)
        r = f["rates"][0]
        self.assertAlmostEqual(r["rate_per_hour"], 7.2, places=2)
        self.assertAlmostEqual(r["to_full_hours"], 19 / 7.2, places=2)  # about 2.6 hours
        self.assertEqual(f["status"], "runs_out_before_reset")
        f2 = meters.forecast(rows, "five_hour", (t1 + dt.timedelta(hours=1)).isoformat(), now=t1)
        self.assertEqual(f2["status"], "resets_first")

    def test_forecast_reset_flat_and_few(self):
        t = [NOW + dt.timedelta(minutes=30 * i) for i in range(4)]
        rows = [{"at": t[0].isoformat(), "five_hour": 90.0}, {"at": t[1].isoformat(), "five_hour": 95.0},
                {"at": t[2].isoformat(), "five_hour": 3.0}, {"at": t[3].isoformat(), "five_hour": 6.0}]
        f = meters.forecast(rows, "five_hour", "", now=t[3])
        self.assertEqual(f["n"], 2)                      # the drop to 3 restarted the segment
        self.assertAlmostEqual(f["rates"][0]["rate_per_hour"], 6.0, places=2)
        flat = [{"at": t[0].isoformat(), "five_hour": 50.0}, {"at": t[1].isoformat(), "five_hour": 50.0}]
        self.assertEqual(meters.forecast(flat, "five_hour", "", now=t[1])["status"], "no_projection")
        one = meters.forecast(flat[:1], "five_hour", "", now=t[1])
        self.assertIn("fewer than two", one["why"])
        stale = meters.forecast(rows, "five_hour", (t[3] - dt.timedelta(hours=1)).isoformat(), now=t[3])
        self.assertEqual(stale["status"], "stale")

    def test_history_dedupes(self):
        cfg = self.cfg
        d = payload(NOW + dt.timedelta(hours=4), NOW + dt.timedelta(days=3))
        m = meters.read_all(cfg, live=False, fixture=d, now=NOW)
        self.assertEqual(meters.append_history(cfg["history_dir"], m), 2)
        self.assertEqual(meters.append_history(cfg["history_dir"], m), 0)
        self.assertEqual(len(meters.load_history(cfg["history_dir"])), 2)

    def test_full_meter_path_into_build(self):
        collect.scan(self.cfg)
        t1 = NOW - dt.timedelta(minutes=50)
        for when, five in ((t1, 75), (NOW, 81)):
            d = payload(NOW + dt.timedelta(hours=4), NOW + dt.timedelta(days=3), five=five)
            m = meters.read_all(self.cfg, live=False, fixture=d, now=when)
            meters.append_history(self.cfg["history_dir"], m)
        # read_all with a fixture does not write the live cache; write the newest one as the live path does
        (Path(self.cfg["history_dir"]) / meters.LIVE_FILE).write_text(json.dumps({"read_utc": NOW.isoformat(), "meters": m}), encoding="utf-8")
        data = collect.build(self.cfg, now_utc=NOW)
        a = data["meters"]["acct-a"]
        self.assertEqual(a["reading"]["five_hour"]["pct"], 81)
        fc = a["forecast"]["five_hour"]
        self.assertEqual(fc["status"], "runs_out_before_reset")
        self.assertAlmostEqual(fc["rates"][0]["rate_per_hour"], 7.2, places=1)
        self.assertIn("five_hour", a["measured"])
        self.assertEqual(data["meters"]["acct-b"]["forecast"]["five_hour"]["status"], "no_projection")

    def test_live_reader_never_leaks_the_token(self):
        fake_value = "synthetic-credential-value-0001"
        home = self.tmp / "homes" / "acct-a"
        (home / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": fake_value}}), encoding="utf-8")
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=10):
            seen["auth"] = req.get_header("Authorization")
            seen["ua"] = req.get_header("User-agent")
            return Resp(json.dumps({"five_hour": {"utilization": 12, "resets_at": "2026-11-19T20:00:00+00:00"}}).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            raw = meters.fetch_raw(home, "usage-mirror-test")
        self.assertEqual(raw["five_hour"]["utilization"], 12)
        self.assertEqual(seen["auth"], "Bearer " + fake_value)         # sent in the header only
        self.assertNotIn(fake_value, json.dumps(raw))
        self.assertEqual(seen["ua"], "usage-mirror-test")

        import urllib.error

        def deny(req, timeout=10):
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", deny):
            err = meters.fetch_raw(home, "x")
        self.assertEqual(err, {"error": "http_401"})
        with mock.patch("urllib.request.urlopen", side_effect=OSError(fake_value)):
            err = meters.fetch_raw(home, "x")
        self.assertEqual(err, {"error": "connection_error"})        # the exception text never travels
        self.assertEqual(meters.fetch_raw(self.tmp / "homes" / "acct-b", "x"), {"error": "no_credentials"})

        # read_all end to end with the patched network: reading is stored without the token anywhere
        cfg = dict(self.cfg, live_meters=True, live_reuse_seconds=300)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            m = meters.read_all(cfg, live=True, now=NOW)
        self.assertEqual(m["acct-a"]["source"], "live")
        self.assertEqual(m["acct-b"]["source"], "none")
        self.assertIn("sign-in file", m["acct-b"]["message"])
        for p in Path(cfg["history_dir"]).glob("*"):
            self.assertNotIn(fake_value.encode(), p.read_bytes())

    def test_saved_fallback_when_live_fails(self):
        home = self.tmp / "homes" / "acct-b"
        ms = int(NOW.timestamp() * 1000)
        (home / ".claude.json").write_text(json.dumps({"cachedUsageUtilization": {
            "fetchedAtMs": ms, "utilization": {"five_hour": {"utilization": 33, "resets_at": "2026-11-19T18:00:00+00:00"}}}}), encoding="utf-8")
        cfg = dict(self.cfg, live_meters=True, live_reuse_seconds=0)
        m = meters.read_all(cfg, live=True, now=NOW)
        self.assertEqual(m["acct-b"]["source"], "saved")
        self.assertEqual(m["acct-b"]["five_hour"]["pct"], 33)
        self.assertIn("may be old", m["acct-b"]["message"])


class OutlierTests(Base):
    def test_run_has_items_and_appends(self):
        collect.scan(self.cfg)
        run = outliers.compute(self.cfg, 12, now=NOW)
        titles = " | ".join(i["title"] for i in run["items"])
        self.assertIn("API-equivalent in the last 12 hours", titles)
        self.assertIn("could not be priced", titles)
        self.assertIn("cold cache rebuild", titles)
        self.assertIn("context compaction", titles)
        n = outliers.append_run(self.cfg["history_dir"], run)
        self.assertEqual(n, 1)
        saved = json.loads((Path(self.cfg["history_dir"]) / "insights.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["hours"], 12)

    def test_empty_window(self):
        collect.scan(self.cfg)
        run = outliers.compute(self.cfg, 1, now=NOW - dt.timedelta(days=20))
        self.assertIn("No responses", run["items"][0]["title"])


class PageTests(Base):
    def build_all(self):
        collect.scan(self.cfg)
        d = collect.build(self.cfg, now_utc=NOW)
        out = Path(self.cfg["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "usage_data.json").write_text(json.dumps(d), encoding="utf-8")
        outliers.append_run(self.cfg["history_dir"], outliers.compute(self.cfg, 12, now=NOW))
        page = out / "usage_mirror.html"
        build_page.build(SKILL / "scripts" / "page_template.html", out / "usage_data.json",
                         Path(self.cfg["history_dir"]) / "insights.json", page)
        return page

    def test_page_builds_and_is_safe(self):
        page = self.build_all()
        html = page.read_text(encoding="utf-8")
        self.assertEqual(html.count("/*__USAGE_DATA__*/"), 0)
        self.assertEqual(len(re.findall(r"<script>", html)), 1)
        self.assertEqual(html.count("</script>"), 1)           # the hostile title could not close the script
        self.assertIn("\\u003c/script>", html)
        self.assertNotRegex(html, r"https?://")                 # no network reference of any kind

    def test_template_placeholder_must_be_unique(self):
        bad = self.tmp / "t.html"
        bad.write_text("<script>const U=/*__USAGE_DATA__*/null; /*__USAGE_DATA__*/null</script>", encoding="utf-8")
        (self.tmp / "d.json").write_text(json.dumps({"generated_local": "x", "sessions": [], "rows": [], "accounts": []}), encoding="utf-8")
        with self.assertRaises(ValueError):
            build_page.build(bad, self.tmp / "d.json", None, self.tmp / "o.html")

    def test_inline_script_syntax_and_behaviour(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        page = self.build_all()
        html = page.read_text(encoding="utf-8")
        script = re.search(r"<script>([\s\S]*?)</script>", html).group(1)
        js = self.tmp / "inline.js"
        js.write_text(script, encoding="utf-8")
        r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([node, str(HERE / "js_smoke.js"), str(page)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertIn("API-equivalent cost", out["tiles"])
        self.assertIn("Demo session one", out["sessions"])
        self.assertIn("&lt;/script&gt;&lt;b&gt;hostile", out["sessions"])   # the title is escaped, not interpreted
        self.assertNotIn("<b>hostile", out["sessions"])
        self.assertIn("claude-sonnet-5", out["models"])
        self.assertIn("unpriced", out["models"])
        self.assertIn("API-equivalent", out["ins"] + out["tiles"])
        self.assertIn("2 accounts", out["sub"])


class LeakScanTests(unittest.TestCase):
    def test_flags_planted_leaks_and_passes_clean(self):
        tmp = Path(tempfile.mkdtemp(prefix="um-leak-"))
        try:
            root = tmp / "pkg"
            root.mkdir()
            (root / "clean.md").write_text("Plain words. Example: 75% to 81% in 50 minutes.\n", encoding="utf-8")
            with mock.patch("sys.stdout", io.StringIO()):
                code = leak_scan.main([str(root), "--terms", str(tmp / "none.json")])
            self.assertEqual(code, 0)
            planted = {
                "email.txt": "write to " + "someone" + "@" + "example.org",
                "path.txt": "C" + ":" + "/" + "Users/x",
                "uuid.txt": "id " + "123e4567-e89b-" + "12d3-a456-426614174000",
                "link.txt": "see claude.ai/" + "artifact/abc",
                "key.txt": "k = " + "sk" + "-ant-" + "abcdefghijklmnop",
                "dash.md": "a " + "\u2014" + " b",
                "money.md": "it cost " + "$" + "1234 in total",
                "pct.md": "usage was 83% today",
            }
            for name, body in planted.items():
                (root / name).write_text(body + "\n", encoding="utf-8")
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                code = leak_scan.main([str(root), "--terms", str(tmp / "none.json")])
            out = buf.getvalue()
            self.assertEqual(code, 1)
            for name in planted:
                self.assertIn("HIT " + name + ":1:", out, name)
            self.assertNotIn("abcdefghijklmnop", out)               # token excerpts are masked
            # owner terms
            terms = tmp / "terms.json"
            terms.write_text(json.dumps({"terms": [{"name": "t", "pattern": "forbidden-word", "allow": "allowed context"}]}), encoding="utf-8")
            for f in root.iterdir():
                f.unlink()
            (root / "a.md").write_text("a forbidden-word here\nforbidden-word in allowed context\n", encoding="utf-8")
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                code = leak_scan.main([str(root), "--terms", str(terms)])
            self.assertEqual(code, 1)
            self.assertIn("a.md:1:", buf.getvalue())
            self.assertNotIn("a.md:2:", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PackageTests(unittest.TestCase):
    def test_version_matches_everywhere(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        fm = re.match(r"---\n([\s\S]*?)\n---", skill).group(1)
        self.assertRegex(fm, r"(?m)^name: usage-mirror$")
        v = re.search(r'(?m)^version: "?([0-9.]+)"?$', fm).group(1)
        self.assertEqual(v, common.VERSION)
        self.assertRegex((SKILL / "CHANGELOG.md").read_text(encoding="utf-8"), r"(?m)^## " + re.escape(v) + r"\b")

    def test_skill_has_required_sections(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("SKILLGARDEN-STANDARD-SECTION", "## The settings rule", "## Contributing upstream", "WHITEPAPER.md"):
            self.assertIn(needle, skill)

    def test_no_machine_specific_paths_or_dashes_in_scripts(self):
        for p in (SKILL / "scripts").glob("*"):
            if p.suffix in {".py", ".html"} and p.name != "leak_scan.py":
                t = p.read_text(encoding="utf-8")
                self.assertNotIn("\u2014", t, p.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
