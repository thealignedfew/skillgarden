"""Settings for the Stagecraft.

Three layers, later wins: the catalog's defaults, the person's own file, a project file.
  person:  <home>/.stagecraft/options.json   (or the folder named in STAGECRAFT_HOME)
  project: .claude/stagecraft.json in the working folder or any folder above it

  options.py status                 has first launch happened; how many options are still on their default
  options.py first-launch           the catalog with each option's 'recommend' text, for the agent's first proposal
  options.py show [--json]          every effective value and where it comes from
  options.py explain <id>           one option in full
  options.py set <id> <value> [--project]    save a choice (validated against the catalog)
  options.py unset <id> [--project]          back to the layer below
  options.py done                   record that the first-launch proposal was shown and answered
  options.py page-config            JSON of the 'page' options, for PB_CONFIG.defaults
Reads and writes only the two option files. No network, no other files."""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "..", "options", "catalog.json")


def load(p):
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def user_path():
    base = os.environ.get("STAGECRAFT_HOME") or os.path.join(os.path.expanduser("~"), ".stagecraft")
    return os.path.join(base, "options.json")


def project_path(create=False):
    d = os.getcwd()
    while True:
        p = os.path.join(d, ".claude", "stagecraft.json")
        if os.path.exists(p):
            return p
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return os.path.join(os.getcwd(), ".claude", "stagecraft.json") if create else None


def save(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def coerce(opt, raw):
    t = opt.get("type")
    if "choices" in opt:
        if raw not in opt["choices"]:
            raise SystemExit("%s: '%s' is not one of %s" % (opt["id"], raw, ", ".join(opt["choices"])))
        return raw
    if t in ("number", "int"):   # 0.3.0: the catalog types layout.measure_ch as "int"; it was returned as text before
        try:
            v = int(raw)
        except ValueError:
            raise SystemExit("%s needs a whole number" % opt["id"])
        rg = opt.get("range")
        if rg and not (rg[0] <= v <= rg[1]):
            raise SystemExit("%s must be between %d and %d" % (opt["id"], rg[0], rg[1]))
        return v
    if t == "map":
        try:
            v = json.loads(raw)
        except ValueError:
            raise SystemExit("%s needs a JSON object, for example {\"Team\": \"blue\"}" % opt["id"])
        if not isinstance(v, dict):
            raise SystemExit("%s needs a JSON object" % opt["id"])
        return v
    return raw


def main(argv):
    cat = load(CATALOG)
    opts = {o["id"]: o for o in cat.get("options", [])}
    if not opts:
        raise SystemExit("catalog not found at " + CATALOG)
    up, pp = user_path(), project_path()
    user, proj = load(up), (load(pp) if pp else {})
    uv, pv = user.get("values", {}), proj.get("values", {})

    def eff(i):
        if i in pv:
            return pv[i], "project"
        if i in uv:
            return uv[i], "yours"
        return opts[i]["default"], "default"

    cmd = argv[0] if argv else "status"
    if cmd == "status":
        own = sum(1 for i in opts if eff(i)[1] != "default")
        print("first launch: %s" % ("done on " + user["first_launch_done"] if user.get("first_launch_done") else "NOT DONE: run 'options.py first-launch' and make the proposal"))
        print("options: %d, set by the person or the project: %d, on their default: %d" % (len(opts), own, len(opts) - own))
        print("your file: %s%s" % (up, "" if os.path.exists(up) else " (not created yet)"))
        if pp:
            print("project file: " + pp)
    elif cmd == "first-launch":
        print(cat.get("first_launch", ""))
        for g in cat.get("groups", []):
            print("\n== " + g)
            for o in cat["options"]:
                if o["group"] != g:
                    continue
                v, src = eff(o["id"])
                print("- %s [%s] now: %s (%s)" % (o["id"], o["applies"], json.dumps(v, ensure_ascii=False), src))
                print("    " + o["title"] + (": " + " | ".join("%s = %s" % kv for kv in o["choices"].items()) if "choices" in o else ""))
                print("    RECOMMEND: " + o["recommend"])
    elif cmd == "show":
        if "--json" in argv:
            print(json.dumps({i: eff(i)[0] for i in opts}, indent=2, ensure_ascii=False))
        else:
            for g in cat.get("groups", []):
                print("== " + g)
                for o in cat["options"]:
                    if o["group"] == g:
                        v, src = eff(o["id"])
                        print("  %-28s %-22s %s" % (o["id"], json.dumps(v, ensure_ascii=False), "" if src == "default" else "(" + src + ")"))
    elif cmd == "explain" and len(argv) > 1 and argv[1] in opts:
        o = opts[argv[1]]
        v, src = eff(o["id"])
        print("%s: %s\nnow: %s (%s); default: %s; acts on: %s" % (o["id"], o["title"], json.dumps(v, ensure_ascii=False), src, json.dumps(o["default"], ensure_ascii=False), o["applies"]))
        for k, d in o.get("choices", {}).items():
            print("  %s = %s" % (k, d))
        print("recommend: " + o["recommend"])
    elif cmd in ("set", "unset") and len(argv) > 1:
        i = argv[1]
        if i not in opts:
            raise SystemExit("no option '%s'. 'options.py show' lists them. If the person wants something no option covers, say so and propose a new option to the skill's owner." % i)
        to_proj = "--project" in argv
        path = project_path(create=True) if to_proj else up
        data = load(path)
        vals = data.setdefault("values", {})
        if cmd == "set":
            rest = [a for a in argv[2:] if a != "--project"]
            if not rest:
                raise SystemExit("set needs a value")
            vals[i] = coerce(opts[i], rest[0])
        else:
            vals.pop(i, None)
        save(path, data)
        print("%s %s in %s" % (i, "= " + json.dumps(vals[i], ensure_ascii=False) if cmd == "set" else "unset", path))
    elif cmd == "done":
        import datetime
        user["first_launch_done"] = datetime.date.today().isoformat()
        user.setdefault("values", {})
        save(up, user)
        print("first launch recorded in " + up)
    elif cmd == "page-config":
        print(json.dumps({i: eff(i)[0] for i, o in opts.items() if o["applies"] == "page"}, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
