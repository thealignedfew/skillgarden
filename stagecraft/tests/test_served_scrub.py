#!/usr/bin/env python3
"""Tests for scripts/served_scrub.py. Run: python tests/test_served_scrub.py [page.html ...]

Part 1: tricky inputs, each with an exact expected output. Part 2 (needs the person's own scrub_terms.txt): every page named on the command line (or, with
none, the Kitchen's parley templates and stagecraft's own pages) is scrubbed and checked three ways: no owner-name
comment is left, every inline script still passes `node --check` (when node is on the path), and what was removed
is nothing but whole comments (the page with those comments deleted by a second, simpler method is identical).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import served_scrub as S  # noqa: E402

REAL = S.OWNER                                   # the person's own list, for the real pages in part 2
S.OWNER = re.compile(r"\bPat\b|Quillfeather|\bpatq\b")      # part 1 uses made-up names, so this file names nobody

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print("FAIL %s\n  want %r\n  got  %r" % (name, want, got))
    else:
        print("ok   " + name)


def sc(t):
    return S.scrub(t)[0]


# ---- part 1: exact cases
check("html comment alone on its lines goes with its lines",
      sc("<p>a</p>\n<!-- Pat 2026-11-04: ruling\n   more -->\n<p>b</p>\n"), "<p>a</p>\n<p>b</p>\n")
check("comment without the name stays", sc("<!-- 2026-11-04 plain note -->\n<p>x</p>"), "<!-- 2026-11-04 plain note -->\n<p>x</p>")
check("css block comment", sc("<style>\n/* Pat 2026-10-28: palette */\na{color:red}\n</style>"), "<style>\na{color:red}\n</style>")
check("js line comment after code keeps the code", sc("<script>\nvar a = 1; // Pat said so\nvar b = 2;\n</script>"),
      "<script>\nvar a = 1;\nvar b = 2;\n</script>")
check("js block comment inside an expression becomes a space", sc("<script>var a = 1 /* Pat */ + 2;</script>"), "<script>var a = 1   + 2;</script>")
check("js block comment inside an expression is gone", "Pat" in sc("<script>var a = 1 /* Pat */ + 2;</script>"), False)
check("// inside a string is not a comment", sc('<script>var u = "http://x.test/Pat"; // Pat\n</script>'), '<script>var u = "http://x.test/Pat";\n</script>')
check("// inside a regex is not a comment", sc("<script>var r = /a\\/\\/b/g; // Pat\nvar q = 1;</script>"), "<script>var r = /a\\/\\/b/g;\nvar q = 1;</script>")
check("quote inside a regex does not open a string", sc("<script>var r = /[\"']/; /* Pat */ var s = 1;</script>"), "<script>var r = /[\"']/;   var s = 1;</script>")
check("regex with a quote keeps the code after it", "var s = 1" in sc("<script>var r = /[\"']/; /* Pat */ var s = 1;</script>"), True)
check("division is not a regex", sc("<script>var a = b / 2; var c = d / 4; // Pat\n</script>"), "<script>var a = b / 2; var c = d / 4;\n</script>")
check("template literal with ${} and a comment-looking text", sc("<script>var t = `a // Pat ${x + `/*`} b`; // Pat\n</script>"), "<script>var t = `a // Pat ${x + `/*`} b`;\n</script>")
check("comment in a template expression is a comment", "Pat" in sc("<script>var t = `a ${ /* Pat */ x } b`;</script>"), False)
check("json script untouched", sc('<script type="application/json">{"u":"//Pat"}</script>'), '<script type="application/json">{"u":"//Pat"}</script>')
check("exempt marker keeps its marker, loses the reason", sc("<!-- artifact-header: exempt (Pat's own word) -->\n<p>x</p>"), "<!-- artifact-header: exempt -->\n<p>x</p>")
check("stagecraft exempt marker", sc("<!-- stagecraft: exempt (Pat asked) -->"), "<!-- stagecraft: exempt -->")
check("name in page text is residual, not removed", S.scrub("<p>Questions for Pat</p><!-- Pat -->")[0], "<p>Questions for Pat</p>")
check("residual reported", len(S.scrub("<p>Questions for Pat</p>")[1]["residual"]), 1)
check("CRLF page keeps its line endings", sc("<p>a</p>\r\n<!-- Pat -->\r\n<p>b</p>\r\n"), "<p>a</p>\r\n<p>b</p>\r\n")
check("surname and folder name count", sc("<!-- Quillfeather -->\n<!-- C:\\Users\\patq\\x -->\n<p>k</p>"), "<p>k</p>")
check("a longer word is not the name", sc("<script>var m = Patrol(1, 2); // note\n</script>"), "<script>var m = Patrol(1, 2); // note\n</script>")
r = S.scrub("<script>var a = 'oops\n</script>")[1]
check("unterminated string: page left alone", (r["ok"], r["reason"]), (False, "unterminated string"))
t = "<script>var a = 1; /* Pat */\n"
check("unterminated script: page left alone", S.scrub(t)[0], t)

# ---- part 2: real pages
def node_check(text):
    node = shutil.which("node")
    if not node:
        return None
    bad = []
    for i, m in enumerate(re.finditer(r"<script(?![^>]*type=[\"']application/json)[^>]*>(.*?)</script>", text, re.S | re.I)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(m.group(1))
        p = subprocess.run([node, "--check", fh.name], capture_output=True, text=True)
        os.unlink(fh.name)
        if p.returncode:
            bad.append((i, p.stderr.strip().splitlines()[0:3]))
    return bad


def independent_strip(text, spans):
    """A second way to the same result: delete the owner-naming comments by span, replace an exempt marker by its bare form,
    and compare with the scrubbed page ignoring blank space."""
    out, at = [], 0
    for s, e, k in spans:
        body = text[s:e]
        if not S.OWNER.search(body):
            continue
        out.append(text[at:s])
        m = S.EXEMPT_COMMENT.match(body)
        if m:
            out.append("<!-- %s: exempt -->" % m.group(1).lower())
        at = e
    out.append(text[at:])
    return re.sub(r"\s+", "", "".join(out))


S.OWNER = REAL
if REAL.pattern == '(?!x)x':
    print('no scrub_terms.txt found: part 2 (real pages) skipped')
    pages = []
else:
    pages = sys.argv[1:]
if not pages and REAL.pattern != '(?!x)x':
    K = os.path.dirname(os.path.dirname(HERE))
    for rel in ("parley/assets/artifact-header-snippet.html", "parley/assets/parley-template.html",
                "parley/assets/moved-page-template.html", "stagecraft/assets/stagecraft-snippet.html",
                "stagecraft/assets/demo-page.html"):
        p = os.path.join(K, rel)
        if os.path.isfile(p):
            pages.append(p)
for p in pages:
    text = open(p, "rb").read().decode("utf-8")
    new, rep = S.scrub(text)
    name = os.path.basename(p)
    check(name + ": lexer reads the page", rep["ok"], True)
    if not rep["ok"]:
        continue
    check(name + ": no owner-name comment left", [1 for s, e, k in S.comment_spans(new) if S.OWNER.search(new[s:e])], [])
    check(name + ": only whole comments removed", re.sub(r"\s+", "", new), independent_strip(text, S.comment_spans(text)))
    if node_check(text) is not None:
        check(name + ": scripts pass node --check before", node_check(text), [])
        check(name + ": scripts pass node --check after", node_check(new), [])
    print("     %s: %d comment(s) removed, %d mention(s) outside comments left" % (name, len(rep["removed"]), len(rep["residual"])))

print("\n%s" % ("ALL PASSED" if not FAILS else "FAILED: " + ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
