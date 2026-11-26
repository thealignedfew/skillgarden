"""Tests for disk_health.py on made-up drive samples. No machine data, no event log, no network."""
import json, os, sys, tempfile, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import disk_health as dh  # noqa: E402


def rec(t, vols, disks):
    return {'t': t.strftime('%Y-%m-%dT%H:%M:%S'), 'vol': vols, 'disk': disks}


def vol(letter, pct, gb=100):
    return {'v': letter, 'freeGB': gb, 'freePct': pct}


def disk(name, r=10.0, w=10.0, idle=90, q=0.1):
    return {'d': name, 'r': r, 'w': w, 'idle': idle, 'q': q}


NOW = datetime.now()


class Space(unittest.TestCase):
    def test_ssd_free_space_lines(self):
        S = [rec(NOW, [vol('C', 8), vol('D', 12), vol('E', 40)], [])]
        find, ok = dh.analyse(S, {}, 0, {'ssd_volumes': ['C', 'D', 'E']})
        text = ' | '.join(find)
        self.assertIn('C: only 8% free', text)
        self.assertIn('D: 12% free', text)
        self.assertTrue(any(o.startswith('E: 40% free') for o in ok))

    def test_without_settings_no_volume_is_called_an_ssd(self):
        S = [rec(NOW, [vol('C', 12), vol('D', 8)], [])]
        find, ok = dh.analyse(S, {}, 0, {})
        self.assertEqual(len(find), 1)               # only the 10 percent line applies
        self.assertIn('D: only 8% free', find[0])
        self.assertNotIn('SSD', find[0])
        self.assertTrue(any('C: 12% free' in o for o in ok))

    def test_no_samples_says_so(self):
        find, ok = dh.analyse([], {}, 0, {})
        self.assertIn('no drive samples', find[0])


class Busy(unittest.TestCase):
    def test_saturated_disk_is_flagged(self):
        S = [rec(NOW, [], [disk('1 c:', idle=5)]) for _ in range(6)]
        find, ok = dh.analyse(S, {}, 0, {})
        self.assertTrue(any('disk 1 c:' in f and 'busy' in f for f in find))

    def test_quiet_disk_is_ok(self):
        S = [rec(NOW, [], [disk('1 c:', idle=95)]) for _ in range(6)]
        find, ok = dh.analyse(S, {}, 0, {})
        self.assertEqual(find, [])


class Endurance(unittest.TestCase):
    def test_over_budget_is_flagged(self):
        # 600 TBW over 5 years is about 337 GB a day; 100 GB in 60 minutes projects to 2400
        find, ok = dh.analyse([rec(NOW, [], [disk('1 c:')])], {'1 c:': 100}, 60, {'rated_tbw': {'1': 600}})
        self.assertTrue(any('on course for 2400 GB/day' in f for f in find))

    def test_under_budget_is_ok(self):
        find, ok = dh.analyse([rec(NOW, [], [disk('1 c:')])], {'1 c:': 1}, 600, {'rated_tbw': {'1': 600}})
        self.assertFalse(any('on course' in f for f in find))
        self.assertTrue(any('on course' in o for o in ok))

    def test_missing_rating_skips_with_a_hint(self):
        find, ok = dh.analyse([rec(NOW, [], [disk('1 c:')])], {'1 c:': 50}, 60, {})
        self.assertTrue(any('rated_tbw' in o for o in ok))
        self.assertFalse(any('on course' in x for x in find + ok))


class Counters(unittest.TestCase):
    def test_none_means_not_available_not_a_fault(self):
        find, ok = dh.judge_storage(None)
        self.assertEqual(find, [])
        self.assertEqual(len(ok), 1)

    def test_wear_temp_and_errors(self):
        st = {'1': {'model': 'X', 'wearPct': 85, 'tempC': 60, 'powerOnHours': 10, 'readErrUncorrected': 0, 'writeErrUncorrected': 0},
              '2': {'model': 'Y', 'wearPct': 5, 'tempC': 75, 'powerOnHours': 10, 'readErrUncorrected': 0, 'writeErrUncorrected': 1},
              '3': {'model': 'Z', 'wearPct': 5, 'tempC': 40, 'powerOnHours': 10}}
        find, ok = dh.judge_storage(st)
        self.assertEqual(len(find), 2)
        self.assertEqual(len(ok), 1)


class Files(unittest.TestCase):
    def test_day_writes_and_recent_samples(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'procmem-%s.jsonl' % NOW.strftime('%Y%m%d'))
            with open(p, 'wb') as fh:
                fh.write(b'\xef\xbb\xbf' + json.dumps(rec(NOW - timedelta(minutes=2), [vol('C', 50)], [disk('1 c:', w=1024)])).encode() + b'\n')
                fh.write(b'not json\n')
                fh.write(json.dumps({'t': NOW.strftime('%Y-%m-%dT%H:%M:%S')}).encode() + b'\n')   # no disk field: skipped
            gb, n = dh.day_writes(d)
            S = dh.recent_samples(d, 10)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(gb['1 c:'], 60.0)       # 1024 MB/s for one minute is 60 GB
        self.assertEqual(len(S), 1)

    def test_drives_json_is_optional_and_tolerant(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(dh.load_drives(d), {})
            with open(os.path.join(d, 'drives.json'), 'w') as fh:
                fh.write('{broken')
            self.assertEqual(dh.load_drives(d), {})


if __name__ == '__main__':
    unittest.main()
