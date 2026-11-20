#!/usr/bin/env python3
r"""check_syntax: extract every inline <script> from the snippet and the demo page and run `node --check` on each.

    python -I -B tests/check_syntax.py

Needs node on the PATH. Scripts are written to a temporary folder and removed afterwards. Exit 0 when all parse.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [os.path.join(ROOT, "assets", "stagecraft-snippet.html"), os.path.join(ROOT, "assets", "demo-page.html")]
node = shutil.which("node")
if not node:
    print("FAIL node not found on the PATH")
    sys.exit(1)
tmp = tempfile.mkdtemp(prefix="stagecraft-syntax-")
bad = 0
for f in FILES:
    html = io.open(f, encoding="utf-8").read()
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    print("%s: %d script block(s), %d bytes" % (os.path.basename(f), len(scripts), sum(len(s) for s in scripts)))
    for i, s in enumerate(scripts):
        p = os.path.join(tmp, "s%d.js" % i)
        io.open(p, "w", encoding="utf-8", newline="\n").write(s)
        r = subprocess.run([node, "--check", p], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ok = r.returncode == 0
        bad += 0 if ok else 1
        print("  %s script %d%s" % ("PASS" if ok else "FAIL", i, "" if ok else ": " + r.stderr.decode()[:300]))
    n = len(re.findall(r"<script[\s>]", html))
    ext = re.findall(r"<script[^>]*\ssrc=", html)
    print("  %s no external script (%d script tags, %d with src)" % ("PASS" if not ext else "FAIL", n, len(ext)))
    bad += 1 if ext else 0
snip = io.open(FILES[0], encoding="utf-8").read()
one = len(re.findall(r"<style>", snip)) == 1 and len(re.findall(r"<script>", snip)) == 1
print("%s the snippet has one <style> and one <script>" % ("PASS" if one else "FAIL"))
bad += 0 if one else 1
shutil.rmtree(tmp, ignore_errors=True)
print("RESULT:", "OK" if not bad else "%d problem(s)" % bad)
sys.exit(1 if bad else 0)
