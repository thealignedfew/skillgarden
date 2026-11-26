"""Tests for build_dashboard.py on made-up data: the figures on the page must equal the figures worked out from the files.

A stub stands in for the stagecraft skill, so no real skill, machine data or network is touched.
"""
import json, os, re, subprocess, sys, tempfile, unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'scripts', 'build_dashboard.py')
NOW = datetime.now()


def iso(t):
    return t.strftime('%Y-%m-%dT%H:%M:%S')


def make_home(d):
    """Samples every 10 s for the last 5 minutes; two strained ones (300 MB free) early on; the newest has 2048 MB free."""
    samples = []
    for k in range(30):
        t = NOW - timedelta(seconds=10 * (30 - k))
        free = 300 if k in (3, 4) else 4000
        if k == 29:
            free = 2048
        samples.append({'t': iso(t), 'availMB': free, 'commitPct': 70.0, 'cpuPct': 20.0, 'fg': 'editor', 'idleSec': 3,
                        'top5': ['hogapp 160.0', 'smallapp 10.0'] if free == 300 else ['smallapp 10.0']})
    with open(os.path.join(d, 'samples-%s.jsonl' % NOW.strftime('%Y%m%d')), 'w', encoding='utf-8') as fh:
        for s in samples:
            fh.write(json.dumps(s) + '\n')
    stamp = lambda m: (NOW - timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S') + ' -05:00'
    with open(os.path.join(d, 'govern.log'), 'w', encoding='utf-8') as fh:
        fh.write(stamp(4) + ' stage1 task APPLY: 5 idle of 9 claude; resident 1000 -> 300 (2s) -> 400 (30s) MB; storm none; failed 0\n')
        fh.write(stamp(3) + ' stage1 task APPLY: 4 idle of 8 claude; resident 800 -> 200 (2s) -> 300 (30s) MB; storm none; failed 0\n')
        fh.write(stamp(2) + ' brake BRAKE: PING 1 mem-ok io-ok\n')
        fh.write(stamp(2) + ' brake BRAKE: PING 2 mem-ok io-ok\n')
        fh.write(stamp(1) + ' brake RELEASE (away, calm or target switched off): PING 1 mem-ok io-ok\n')
    with open(os.path.join(d, 'brake.json'), 'w', encoding='utf-8') as fh:
        json.dump({'targets': [{'name': 'pingtool', 'match': '', 'helpers': [], 'enabled': True, 'approved': 'test', 'why': 'test'}]}, fh)
    return samples


def stub_stagecraft(d):
    p = os.path.join(d, 'stage', 'scripts')
    os.makedirs(p)
    with open(os.path.join(p, 'inject_stagecraft.py'), 'w') as fh:
        fh.write("print('stub injected')\n")
    return os.path.join(d, 'stage')


def run(args, **kw):
    return subprocess.run([sys.executable, '-I', SCRIPT] + args, capture_output=True, text=True, timeout=120, **kw)


@unittest.skipIf(NOW.hour == 0 and NOW.minute < 10, 'a build just after midnight splits "today" across two days')
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.samples = make_home(d)
        cls.out = os.path.join(d, 'page.html')
        r = run(['--samples', d, '--log', os.path.join(d, 'govern.log'), '--config', os.path.join(d, 'brake.json'),
                 '--out', cls.out, '--days', '2', '--stagecraft', stub_stagecraft(d)])
        cls.r = r
        cls.html = ''
        if os.path.exists(cls.out):
            with open(cls.out, encoding='utf-8') as fh:
                cls.html = fh.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tile(self, label):
        m = re.search(r'<span class="lbl">' + re.escape(label) + r'</span><span class="v">([^<]*)</span>', self.html)
        self.assertIsNotNone(m, label)
        return m.group(1)

    def test_it_ran(self):
        self.assertEqual(self.r.returncode, 0, self.r.stderr)
        self.assertIn('30 samples', self.r.stdout)
        self.assertIn('2 trims', self.r.stdout)

    def test_free_ram_now_is_the_newest_sample(self):
        self.assertEqual(self.tile('Free RAM now'), '2.0 GB')

    def test_lowest_free_ram_today(self):
        self.assertEqual(self.tile('Lowest free RAM today'), '300 MB')

    def test_struggling_last_hour(self):
        self.assertEqual(self.tile('Struggling, last hour'), '7%')      # 2 of 30 samples

    def test_trims_today(self):
        self.assertEqual(self.tile('Trims today'), '2')
        m = re.search(r'Trims today</span><span class="v">2</span><span class="s">([\d.]+) GB held off', self.html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), '1.1')        # (1000-400) + (800-300) = 1100 MB

    def test_brakes_today_counts_slowdowns_only(self):
        self.assertEqual(self.tile('Brakes today'), '2')

    def test_heat_grid_counts_match_the_files(self):
        cells = {}
        for s in self.samples:
            t = datetime.fromisoformat(s['t'])
            k = (t.date(), t.hour)
            c = cells.setdefault(k, [0, 0])
            c[0] += 1
            c[1] += 1 if s['availMB'] < 500 else 0
        for (day, hour), (n, b) in cells.items():
            if b:
                self.assertIn('%s %02d:00, %d of %d samples struggling' % (day.strftime('%a %m-%d'), hour, b, n), self.html)

    def test_suggestion_names_the_busy_program_only(self):
        self.assertIn('hogapp', self.html)
        self.assertNotIn('>smallapp<', self.html)

    def test_no_private_names_on_the_page(self):
        for bad in ("E:" + chr(92), "C:" + chr(92) + "Users", "@"):
            self.assertNotIn(bad, self.html)


class NoStagecraft(unittest.TestCase):
    def test_stops_with_a_message_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'page.html')
            r = run(['--samples', d, '--out', out, '--stagecraft', os.path.join(d, 'absent')])
            self.assertEqual(r.returncode, 2)
            self.assertIn('needs the stagecraft skill', r.stdout)
            self.assertFalse(os.path.exists(out))


if __name__ == '__main__':
    unittest.main()
