"""brake_suggest.py  ramgovern: which processes are worth a brake?

Reads the samples written by sampler.ps1 (one JSON line every few seconds: free RAM, commit, total processor use, the
application in front, the five busiest processes) and counts, over the last N days, how often each process was among the
busiest with at least half a core while the machine was struggling. A process that is often the application in front is
your own work and is not suggested; nor is anything on the protected list or already a target. This only suggests. A
process becomes a brake target only when you say yes and brake.json records it.

"Struggling" is any of these on a sample (each limit can be changed on the command line):
  free memory under --free-mb (default 500), commit charge over --commit-pct (default 95),
  total processor use over --cpu-pct (default 90), or, when a sample carries it, late desktop frames over --late-pct (default 20).
A field a sample does not carry never counts.

  python brake_suggest.py [--days 7] [--json] [--samples <folder>] [--config <brake.json>]
      [--free-mb 500] [--commit-pct 95] [--cpu-pct 90] [--late-pct 20]

The folder defaults to the ramgovern home: the folder named by the environment variable RAMGOVERN_HOME, or else the
folder holding govern.json (this script's folder or the one above it), or else .threadops/ramgovern under your user
profile. brake.json is read from the same folder.
"""
import argparse, glob, json, os, statistics
from datetime import datetime, timedelta

PROTECTED = {'claude', 'code', 'explorer', 'dwm', 'csrss', 'winlogon', 'lsass', 'services', 'svchost', 'system', 'smss',
             'wininit', 'msmpeng', 'audiodg', 'powershell', 'pwsh', 'conhost', 'windowsterminal', 'zoom', 'chrome', 'msedge',
             'idle', 'memory compression', 'registry', 'python', 'node'}
WHY_PROTECTED = 'python and node are the sessions\' own tools; braking them slows the agents themselves.'


def home():
    h = os.environ.get('RAMGOVERN_HOME')
    if h:
        return h
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.dirname(here)):
        if os.path.exists(os.path.join(d, 'govern.json')):
            return d
    return os.path.join(os.path.expanduser('~'), '.threadops', 'ramgovern')


def load_samples(folder, days):
    cut = datetime.now() - timedelta(days=days)
    out = []
    for f in sorted(glob.glob(os.path.join(folder, 'samples-*.jsonl'))):
        try:
            d = datetime.strptime(os.path.basename(f)[8:16], '%Y%m%d')
        except ValueError:
            continue
        if d < cut - timedelta(days=1):
            continue
        with open(f, encoding='utf-8-sig', errors='replace') as fh:
            for line in fh:
                try:
                    s = json.loads(line)
                    if datetime.fromisoformat(s['t']) >= cut:
                        out.append(s)
                except Exception:
                    continue
    return out


def struggling(s, free_mb=500, commit_pct=95, cpu_pct=90, late_pct=20):
    """True when a sample shows the machine under strain. A missing field never counts."""
    def num(k):
        v = s.get(k)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    a, c, p, l = num('availMB'), num('commitPct'), num('cpuPct'), num('latePct')
    return ((a is not None and a < free_mb) or (c is not None and c > commit_pct)
            or (p is not None and p > cpu_pct) or (l is not None and l > late_pct))


def suggest(samples, targets, **limits):
    bad = [s for s in samples if struggling(s, **limits)]
    fg = {}
    for s in samples:
        k = (s.get('fg') or '').lower()
        fg[k] = fg.get(k, 0) + 1
    seen, when = {}, {}
    for s in bad:
        for item in s.get('top5') or []:
            try:
                name, cpu = item.rsplit(' ', 1)
                cpu = float(cpu)
            except ValueError:
                continue
            if cpu < 50:
                continue
            seen.setdefault(name.lower(), []).append(cpu)
            when.setdefault(name.lower(), []).append(s['t'])
    rows = []
    tset = {t.lower() for t in targets}
    for name, cpus in seen.items():
        share = len(cpus) / max(1, len(bad))
        fg_share = fg.get(name, 0) / max(1, len(samples))
        if name in PROTECTED:
            verdict = 'protected'
        elif name in tset:
            verdict = 'already a target'
        elif fg_share > 0.05:
            verdict = 'your own app (often in front)'
        elif share >= 0.15:
            verdict = 'suggest'
        else:
            verdict = 'watch'
        rows.append({'name': name, 'bad_share_pct': round(100 * share, 1), 'median_cpu_pct': round(statistics.median(cpus), 1),
                     'bad_samples': len(cpus), 'foreground_pct': round(100 * fg_share, 1), 'verdict': verdict,
                     'peak_cpu_pct': round(max(cpus), 1), 'first_seen': min(when[name])[:16].replace('T', ' '),
                     'last_seen': max(when[name])[:16].replace('T', ' '), 'hours': len({w[:13] for w in when[name]})})
    rows.sort(key=lambda r: -r['bad_samples'])
    return {'samples': len(samples), 'bad_samples': len(bad), 'rows': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--samples', default=home())
    ap.add_argument('--config', default=os.path.join(home(), 'brake.json'))
    ap.add_argument('--free-mb', type=float, default=500)
    ap.add_argument('--commit-pct', type=float, default=95)
    ap.add_argument('--cpu-pct', type=float, default=90)
    ap.add_argument('--late-pct', type=float, default=20)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    targets = []
    if os.path.exists(a.config):
        with open(a.config, encoding='utf-8-sig') as fh:
            targets = [t['name'] for t in json.load(fh).get('targets', [])]
    r = suggest(load_samples(a.samples, a.days), targets, free_mb=a.free_mb, commit_pct=a.commit_pct,
                cpu_pct=a.cpu_pct, late_pct=a.late_pct)
    if a.json:
        print(json.dumps(r, indent=1))
        return
    print(f"{r['samples']} samples over {a.days} days, {r['bad_samples']} while the machine was struggling")
    for x in r['rows'][:15]:
        print(f"{x['name']:28} in {x['bad_share_pct']:5.1f}% of bad samples, median {x['median_cpu_pct']:6.1f}% cpu, "
              f"in front {x['foreground_pct']:4.1f}%  -> {x['verdict']}")


if __name__ == '__main__':
    main()
