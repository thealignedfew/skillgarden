"""Tests for brake_suggest.py on made-up samples. No machine data, no network."""
import json, os, sys, tempfile, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import brake_suggest as bs  # noqa: E402


def sample(t, avail=4000, fg='editor', top5=None, **extra):
    s = {'t': t.strftime('%Y-%m-%dT%H:%M:%S'), 'availMB': avail, 'fg': fg, 'top5': top5 or []}
    s.update(extra)
    return s


class Struggling(unittest.TestCase):
    def test_free_memory(self):
        self.assertTrue(bs.struggling({'availMB': 300}))
        self.assertFalse(bs.struggling({'availMB': 2000}))

    def test_missing_fields_never_count(self):
        self.assertFalse(bs.struggling({}))
        self.assertFalse(bs.struggling({'t': 'x', 'fg': 'a'}))

    def test_each_signal(self):
        self.assertTrue(bs.struggling({'commitPct': 97}))
        self.assertTrue(bs.struggling({'cpuPct': 95}))
        self.assertTrue(bs.struggling({'latePct': 30}))
        self.assertFalse(bs.struggling({'commitPct': 80, 'cpuPct': 50, 'latePct': 2, 'availMB': 5000}))

    def test_bool_and_text_are_not_numbers(self):
        self.assertFalse(bs.struggling({'availMB': True}))
        self.assertFalse(bs.struggling({'cpuPct': '99'}))


class Suggest(unittest.TestCase):
    def setUp(self):
        base = datetime.now() - timedelta(hours=2)
        self.samples = []
        for i in range(100):
            t = base + timedelta(seconds=15 * i)
            if i < 40:   # the first 40 samples are strained
                self.samples.append(sample(t, avail=200, fg='editor' if i % 5 == 0 else 'browser',
                                           top5=['bighog 150.0', 'python 120.0', 'editor 80.0', 'smallfry 10.0']))
            else:
                self.samples.append(sample(t, avail=5000, fg='editor' if i % 2 == 0 else 'browser'))

    def test_verdicts(self):
        r = bs.suggest(self.samples, targets=[])
        v = {x['name']: x['verdict'] for x in r['rows']}
        self.assertEqual(r['bad_samples'], 40)
        self.assertEqual(v['bighog'], 'suggest')
        self.assertEqual(v['python'], 'protected')
        self.assertEqual(v['editor'], 'your own app (often in front)')
        self.assertNotIn('smallfry', v)      # under half a core is never listed

    def test_existing_target_is_not_suggested(self):
        r = bs.suggest(self.samples, targets=['BigHog'])
        self.assertEqual({x['name']: x['verdict'] for x in r['rows']}['bighog'], 'already a target')

    def test_no_strain_no_rows(self):
        calm = [sample(datetime.now(), avail=9000, top5=['bighog 300.0'])] * 10
        self.assertEqual(bs.suggest(calm, [])['rows'], [])

    def test_limits_can_move(self):
        r = bs.suggest(self.samples, [], free_mb=100)
        self.assertEqual(r['bad_samples'], 0)


class Load(unittest.TestCase):
    def test_reads_samples_with_bom_and_skips_bad_lines(self):
        now = datetime.now()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'samples-%s.jsonl' % now.strftime('%Y%m%d'))
            with open(p, 'wb') as fh:
                fh.write(b'\xef\xbb\xbf' + json.dumps(sample(now - timedelta(minutes=1))).encode() + b'\n')
                fh.write(b'not json\n')
                fh.write(json.dumps(sample(now - timedelta(days=30))).encode() + b'\n')   # too old
            got = bs.load_samples(d, 7)
        self.assertEqual(len(got), 1)


if __name__ == '__main__':
    unittest.main()
