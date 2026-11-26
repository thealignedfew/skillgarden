"""disk_health.py  ramgovern: are your drives being thrashed, or running short of room?

Read-only. It reads:
  - procmem-YYYYMMDD.jsonl, the brake's per-minute sampler: per-disk read and write MB/s, percent idle and queue, and
    per-volume free space
  - the System event log for the last 24 hours: drive resets and disk errors (stornvme 129, disk 7/51/153/157, Ntfs 55/98)
  - the drives' own wear, temperature and error counters, where Windows lets an ordinary user read them
and prints one line per finding, with OK lines for what is fine.

Settings, all optional, in drives.json beside the other ramgovern files:
  {"ssd_volumes": ["C", "D"], "rated_tbw": {"1": 600, "2": 1200}}
  ssd_volumes: the drive letters that are SSDs. Their free space is checked against the SSD guidance below. Without it, every
               volume is checked against the 10 percent line only, and no volume is called an SSD.
  rated_tbw:   disk number -> the drive maker's rated terabytes written. Without it the write-endurance line is skipped.
Rules of thumb used (common SSD guidance, not vendor-specific):
  - an SSD below 15 percent free slows writes and wears faster (less room for its fast cache and wear levelling); below 10
    percent is flagged.
  - a drive under 20 percent idle for most of the last 10 minutes is saturated: everything that reads it waits.
  - daily writes are compared with the rated endurance spread over 5 years (TBW / 1825 days).
  - wear 80 percent or more, any uncorrected error, or a temperature over 70 C is flagged.

  python disk_health.py [--minutes 10] [--json] [--home <folder>]

The ramgovern home is the folder named by the environment variable RAMGOVERN_HOME, or else the folder holding govern.json
(this script's folder or the one above it), or else .threadops/ramgovern under your user profile.
"""
import argparse, glob, json, os, subprocess
from datetime import datetime, timedelta


def home():
    h = os.environ.get('RAMGOVERN_HOME')
    if h:
        return h
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.dirname(here)):
        if os.path.exists(os.path.join(d, 'govern.json')):
            return d
    return os.path.join(os.path.expanduser('~'), '.threadops', 'ramgovern')


def load_drives(folder):
    p = os.path.join(folder, 'drives.json')
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding='utf-8-sig') as fh:
            return json.load(fh)
    except Exception:
        return {}


def recent_samples(folder, minutes):
    cut = datetime.now() - timedelta(minutes=minutes)
    out = []
    for f in sorted(glob.glob(os.path.join(folder, 'procmem-*.jsonl')))[-2:]:
        with open(f, encoding='utf-8-sig', errors='replace') as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    if datetime.fromisoformat(r['t'][:19]) >= cut and r.get('disk'):
                        out.append(r)
                except Exception:
                    continue
    return out


def day_writes(folder, day=None):
    """GB written per disk today, estimated from the per-minute samples (each 2-second rate stands for its minute)."""
    gb = {}
    f = os.path.join(folder, 'procmem-' + (day or datetime.now()).strftime('%Y%m%d') + '.jsonl')
    if not os.path.exists(f):
        return gb, 0
    n = 0
    with open(f, encoding='utf-8-sig', errors='replace') as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get('disk'):
                continue
            n += 1
            for d in r['disk']:
                gb[d['d']] = gb.get(d['d'], 0) + d['w'] * 60 / 1024
    return gb, n


def events(hours=24):
    ps = ("$e=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='stornvme','disk','Ntfs';StartTime=(Get-Date).AddHours(-%d)} "
          "-ErrorAction SilentlyContinue | Where-Object { $_.Id -in 129,7,51,153,157,55,98 }); "
          "$e | Group-Object ProviderName,Id | ForEach-Object { $_.Name + ' x' + $_.Count + ' last ' + $_.Group[0].TimeCreated.ToString('s') }") % hours
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, timeout=60)
        return [l for l in r.stdout.decode('utf-8', 'replace').splitlines() if l.strip()]
    except Exception as e:
        return [f'event read failed: {e}']


def storage_now():
    """Wear, temperature and error counters for each physical disk, or None when Windows does not give them to this user."""
    ps = ("$o=@(Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object { $c=$_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
          "if ($c) { [pscustomobject]@{disk=$_.DeviceId;model=$_.FriendlyName;wearPct=$c.Wear;tempC=$c.Temperature;powerOnHours=$c.PowerOnHours;"
          "readErrUncorrected=$c.ReadErrorsUncorrected;writeErrUncorrected=$c.WriteErrorsUncorrected} } }); if ($o.Count) { $o | ConvertTo-Json -Compress }")
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, timeout=60)
        txt = r.stdout.decode('utf-8', 'replace').strip()
        if not txt:
            return None
        data = json.loads(txt)
        return {str(x['disk']): x for x in (data if isinstance(data, list) else [data])}
    except Exception:
        return None


def analyse(S, gb, n, drives, minutes=10):
    """Pure function: samples, GB written today and the sample count, the settings -> (findings, ok lines)."""
    find, ok = [], []
    ssd = {str(v).upper().rstrip(':') for v in drives.get('ssd_volumes', [])}
    tbw = {str(k): v for k, v in (drives.get('rated_tbw') or {}).items()}
    if not S:
        find.append(f'no drive samples in the last {minutes} min (is the brake running?)')
    else:
        last = S[-1]
        for v in last.get('vol', []):
            kind = 'SSD' if v['v'].upper() in ssd else 'drive'
            if v['freePct'] < 10:
                tail = ': SSD slows and wears faster below 10-15%' if kind == 'SSD' else ': very little room left'
                find.append(f"{v['v']}: only {v['freePct']}% free ({v['freeGB']} GB){tail}")
            elif v['freePct'] < 15 and kind == 'SSD':
                find.append(f"{v['v']}: {v['freePct']}% free ({v['freeGB']} GB): getting low for an SSD")
            else:
                ok.append(f"{v['v']}: {v['freePct']}% free")
        names = sorted({d['d'] for r in S for d in r['disk']})
        for nm in names:
            rows = [d for r in S for d in r['disk'] if d['d'] == nm]
            busy = sum(1 for d in rows if d['idle'] < 20)
            avg_r = sum(d['r'] for d in rows) / len(rows)
            avg_w = sum(d['w'] for d in rows) / len(rows)
            line = f"disk {nm}: busy (under 20% idle) in {busy} of {len(rows)} samples, avg read {avg_r:.1f} MB/s, write {avg_w:.1f} MB/s"
            (find if busy > len(rows) / 2 else ok).append(line)
    if not tbw:
        ok.append('write endurance: add rated_tbw to drives.json to compare daily writes with the drive maker\'s rating')
    for d, g in sorted(gb.items()):
        cap = tbw.get(d.split()[0])
        if cap and n:
            budget = cap * 1024 / 1825
            proj = g * 1440 / n
            line = f"disk {d}: about {g:.0f} GB written today over {n} min sampled, on course for {proj:.0f} GB/day vs a 5-year budget of {budget:.0f} GB/day"
            (find if proj > budget else ok).append(line)
    return find, ok


def judge_storage(st):
    find, ok = [], []
    if st is None:
        ok.append('wear and temperature: Windows did not give this user the drives\' own counters (an administrator may read them)')
        return find, ok
    for k, r in st.items():
        bad = []
        if (r.get('wearPct') or 0) >= 80: bad.append(f"wear {r['wearPct']}%")
        if (r.get('tempC') or 0) > 70: bad.append(f"temp {r['tempC']} C")
        if (r.get('readErrUncorrected') or 0) or (r.get('writeErrUncorrected') or 0): bad.append('uncorrected errors')
        line = f"disk {k} {r.get('model')}: wear {r.get('wearPct')}%, {r.get('tempC')} C, {r.get('powerOnHours')} h"
        (find if bad else ok).append(line + (' -> ' + ', '.join(bad) if bad else ''))
    return find, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutes', type=int, default=10)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--home', default=home())
    a = ap.parse_args()
    S = recent_samples(a.home, a.minutes)
    gb, n = day_writes(a.home)
    find, ok = analyse(S, gb, n, load_drives(a.home), a.minutes)
    for e in events():
        find.append('drive event: ' + e)
    f2, o2 = judge_storage(storage_now())
    find += f2
    ok += o2
    if a.json:
        print(json.dumps({'findings': find, 'ok': ok}, indent=1))
        return
    for f in find:
        print('FLAG ' + f)
    for o in ok:
        print('ok   ' + o)


if __name__ == '__main__':
    main()
