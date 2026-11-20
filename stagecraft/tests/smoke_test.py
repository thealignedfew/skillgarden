#!/usr/bin/env python3
r"""smoke_test: run the settings script, the injector and the publish check on a machine that has none of your folders.

    python tests/smoke_test.py

It copies the skill into a fresh temporary folder, points HOME, USERPROFILE, APPDATA, LOCALAPPDATA, XDG_CONFIG_HOME,
STAGECRAFT_HOME and STAGECRAFT_GATE_LOG at empty folders inside it, runs from an empty working folder, and checks that:
  * the settings script shows the catalog defaults, saves a choice to the person's file and a project choice to the project file,
    refuses a value the catalog does not allow, and writes nothing else;
  * the injector adds Stagecraft to a plain page, and a second run changes nothing;
  * the publish check refuses a page without the marks, lets an injected page through, ignores other tools and other file types,
    and logs to the path it was given;
  * the version in SKILL.md, the include file and the demo page is the same;
  * nothing printed names your real home folder, and your real ~/.stagecraft files were not touched.
Needs Python 3.8 or later. The temporary folder is removed at the end (set STAGECRAFT_KEEP=1 to keep it). Exit 0 when all pass.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)
    if not cond and detail:
        print("     " + str(detail)[-600:].replace("\n", "\n     "))


def stat_of(p):
    try:
        s = os.stat(p)
        return (s.st_size, s.st_mtime_ns)
    except OSError:
        return None


def main():
    real_home = os.path.expanduser("~")
    real_files = [os.path.join(real_home, ".stagecraft", "options.json"), os.path.join(real_home, ".stagecraft", "gate.log")]
    before = [stat_of(p) for p in real_files]
    scratch = tempfile.mkdtemp(prefix="stagecraft-smoke-")
    try:
        skill = os.path.join(scratch, "skill")
        home = os.path.join(scratch, "home")
        work = os.path.join(scratch, "work")
        for d in (home, work, os.path.join(home, "AppData", "Roaming"), os.path.join(home, "AppData", "Local"), os.path.join(home, ".config")):
            os.makedirs(d, exist_ok=True)
        shutil.copytree(ROOT, skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = dict(os.environ)
        for k in ("CLAUDE_CONFIG_DIR", "STAGECRAFT_SNIPPET", "PYTHONPATH", "HOMEDRIVE", "HOMEPATH"):
            env.pop(k, None)
        env.update({"HOME": home, "USERPROFILE": home, "APPDATA": os.path.join(home, "AppData", "Roaming"),
                    "LOCALAPPDATA": os.path.join(home, "AppData", "Local"), "XDG_CONFIG_HOME": os.path.join(home, ".config"),
                    "STAGECRAFT_HOME": os.path.join(home, ".stagecraft"), "STAGECRAFT_GATE_LOG": os.path.join(home, "gate.log"),
                    "PYTHONIOENCODING": "utf-8"})
        outputs = []

        def run(args, stdin=None):
            r = subprocess.run([PY, "-X", "utf8", "-B"] + args, input=stdin, capture_output=True, encoding="utf-8", errors="replace",
                               env=env, cwd=work, timeout=120)
            outputs.append(r.stdout + r.stderr)
            return r

        opt = os.path.join(skill, "scripts", "options.py")
        inj = os.path.join(skill, "scripts", "inject_stagecraft.py")
        gate = os.path.join(skill, "hooks", "stagecraft_gate.py")
        user_file = os.path.join(home, ".stagecraft", "options.json")
        cat = json.load(io.open(os.path.join(skill, "options", "catalog.json"), encoding="utf-8"))
        defaults = {o["id"]: o["default"] for o in cat["options"]}

        # ---- the settings script
        r = run([opt, "status"])
        check("options status: first launch is not done, no file is created by looking", r.returncode == 0 and "NOT DONE" in r.stdout and not os.path.exists(user_file), r.stdout + r.stderr)
        r = run([opt, "show", "--json"])
        try:
            shown = json.loads(r.stdout)
        except ValueError:
            shown = None
        check("options show: every option is on its catalog default on a fresh machine", r.returncode == 0 and shown == defaults, r.stdout[:300] + r.stderr)
        r = run([opt, "page-config"])
        try:
            pc = json.loads(r.stdout)
        except ValueError:
            pc = None
        check("options page-config: JSON of the page options only", isinstance(pc, dict) and pc and all(
            o["applies"] == "page" for o in cat["options"] if o["id"] in pc) and len(pc) == sum(1 for o in cat["options"] if o["applies"] == "page"), r.stdout[:200] + r.stderr)
        r = run([opt, "set", "numbers.negatives", "minus"])
        saved = json.load(io.open(user_file, encoding="utf-8")) if os.path.exists(user_file) else {}
        check("options set: a choice is saved to the person's file, inside the scratch home", r.returncode == 0 and saved.get("values", {}).get("numbers.negatives") == "minus", r.stdout + r.stderr)
        r = run([opt, "show", "--json"])
        check("options show: the saved choice wins over the default", json.loads(r.stdout).get("numbers.negatives") == "minus", r.stdout[:200])
        r = run([opt, "set", "numbers.negatives", "purple"])
        saved = json.load(io.open(user_file, encoding="utf-8"))
        check("options set: a value the catalog does not allow is refused and not saved", saved["values"]["numbers.negatives"] == "minus", r.stdout + r.stderr)
        r = run([opt, "set", "no.such.option", "x"])
        check("options set: an unknown option is refused", r.returncode != 0, r.stdout + r.stderr)
        r = run([opt, "set", "check.mode", "refuse", "--project"])
        proj_file = os.path.join(work, ".claude", "stagecraft.json")
        check("options set --project: written to .claude/stagecraft.json in the working folder", r.returncode == 0 and os.path.exists(proj_file), r.stdout + r.stderr)
        r = run([opt, "show", "--json"])
        check("options show: the project file wins over the person's file and the default", json.loads(r.stdout).get("check.mode") == "refuse", r.stdout[:200])
        run([opt, "unset", "numbers.negatives"])
        r = run([opt, "show", "--json"])
        check("options unset: back to the default", json.loads(r.stdout).get("numbers.negatives") == defaults["numbers.negatives"], r.stdout[:200])
        r = run([opt, "done"])
        check("options done: first launch is recorded", r.returncode == 0 and "first_launch_done" in io.open(user_file, encoding="utf-8").read(), r.stdout + r.stderr)

        # ---- the injector
        page = os.path.join(work, "smoke.html")
        io.open(page, "w", encoding="utf-8", newline="\n").write(
            '<!doctype html>\n<html><head><meta charset="utf-8"><title>Smoke page</title></head>\n<body><h1>Smoke page</h1>\n'
            "<table><tr><th>Item</th><th>Count</th></tr><tr><td>Loaves</td><td>12</td></tr></table>\n</body></html>\n")
        r = run([inj, page, "--seat", "tester", "--session", "demo-session-id", "--key", "smoke-page", "--account", "demo"])
        text = io.open(page, encoding="utf-8").read()
        marks = all(m in text for m in ('data-artifact-header', 'data-playbook=', 'id="pb-options"', "PB_CONFIG"))
        check("inject: a plain page gets the header, the options panel, the version and the page config", r.returncode == 0 and marks, r.stdout + r.stderr)
        check("inject: the author values land in the page config", "tester" in text and "demo-session-id" in text and "smoke-page" in text)
        first = io.open(page, "rb").read()
        r = run([inj, page, "--seat", "tester", "--session", "demo-session-id", "--key", "smoke-page"])
        check("inject: a second run changes nothing", r.returncode == 0 and "unchanged" in r.stdout and io.open(page, "rb").read() == first, r.stdout + r.stderr)

        # ---- the publish check
        def gate_run(tool, path):
            return run([gate], stdin=json.dumps({"tool_name": tool, "tool_input": {"file_path": path}}))

        bare = os.path.join(work, "bare.html")
        io.open(bare, "w", encoding="utf-8", newline="\n").write("<!doctype html><html><head><title>Bare</title></head><body><p>No marks.</p></body></html>\n")
        r = gate_run("Artifact", bare)
        check("gate: a page without the marks is refused with the missing marks named", r.returncode == 0 and '"permissionDecision": "deny"' in r.stdout and "data-artifact-header" in r.stdout, r.stdout + r.stderr)
        r = gate_run("Artifact", page)
        check("gate: the injected page is allowed (reminders at most)", r.returncode == 0 and '"deny"' not in r.stdout, r.stdout + r.stderr)
        r = gate_run("Read", bare)
        check("gate: another tool is ignored, nothing is printed", r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr)
        md = os.path.join(work, "notes.md")
        io.open(md, "w", encoding="utf-8", newline="\n").write("# Notes\n")
        r = gate_run("Artifact", md)
        check("gate: a Markdown file is ignored, nothing is printed", r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr)
        r = run([gate], stdin="this is not json")
        check("gate: unreadable input fails open (exit 0, nothing printed)", r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr)
        run([opt, "set", "check.mode", "off", "--project"])          # the project file (refuse, set above) wins over the person's file
        r = gate_run("Artifact", bare)
        check("gate: check.mode off lets the bare page through", r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr)
        log = os.path.join(home, "gate.log")
        lines = io.open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        check("gate: one log line per decision, at the path it was given", len(lines) >= 4 and any("DENY" in x for x in lines) and any("ALLOW" in x for x in lines), "\n".join(lines))

        # ---- the pieces agree with each other
        def first_match(path, rx):
            m = re.search(rx, io.open(os.path.join(skill, path), encoding="utf-8").read())
            return m.group(1) if m else None
        v_skill = first_match("SKILL.md", r"Version (\d+\.\d+\.\d+)\.")
        v_snip = first_match(os.path.join("assets", "stagecraft-snippet.html"), r'PB\.version = "([^"]+)"')
        v_demo = first_match(os.path.join("assets", "demo-page.html"), r'PB\.version = "([^"]+)"')
        check("the version is the same in SKILL.md, the include file and the demo page", v_skill and v_skill == v_snip == v_demo, (v_skill, v_snip, v_demo))
        check("the injected page carries that version", ('data-playbook="%s"' % v_snip) in text, v_snip)

        # ---- the standalone checks
        r = run([os.path.join(skill, "tests", "contrast_check.py")])
        check("contrast_check: the palette reaches its contrast floors", r.returncode == 0 and "RESULT: OK" in r.stdout, r.stdout[-400:] + r.stderr)
        if shutil.which("node"):
            r = run([os.path.join(skill, "tests", "check_syntax.py")])
            check("check_syntax: every inline script parses with node --check", r.returncode == 0 and "RESULT: OK" in r.stdout, r.stdout[-400:] + r.stderr)
        else:
            print("SKIP check_syntax (node is not on the PATH)")

        # ---- nothing leaked out of the scratch folder
        blob = "\n".join(outputs)
        for form in (scratch, scratch.replace("\\", "/"), scratch.replace("/", "\\")):          # the scratch folder may itself sit under your home
            blob = blob.replace(form, "<scratch>")
        check("nothing printed names your real home folder (outside the scratch folder)", real_home.lower() not in blob.lower(), real_home)
        check("your real ~/.stagecraft files were not touched", [stat_of(p) for p in real_files] == before)
        outside = [d for d in (os.path.join(real_home, ".stagecraft"),) if os.path.exists(d) and stat_of(os.path.join(d, "options.json")) != before[0]]
        check("no settings file appeared or changed outside the scratch folder", not outside)
    finally:
        if os.environ.get("STAGECRAFT_KEEP"):
            print("kept: " + scratch)
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    failed = RESULTS.count(False)
    print("RESULT: %s (%d checks, %d failed)" % ("OK" if not failed else "FAILED", len(RESULTS), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
