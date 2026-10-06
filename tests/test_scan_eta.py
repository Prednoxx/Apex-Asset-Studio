"""The scan time-left estimate follows the recent pace and words it simply."""
import unittest

from apex_asset_studio.ui.common import ScanEta


class ScanEtaTests(unittest.TestCase):
    def test_recent_pace(self):
        now = [0.0]
        eta = ScanEta(clock=lambda: now[0])
        result = None
        for i in range(1, 101):  # 2 seconds per package, 1000 packages
            now[0] = i * 2.0
            result = eta.update(i, 1000)
        self.assertAlmostEqual(result, 900 * 2.0, delta=60)

    def test_waits_for_enough_samples(self):
        now = [0.0]
        eta = ScanEta(clock=lambda: now[0])
        now[0] = 1; self.assertIsNone(eta.update(1, 100))

    def test_wording(self):
        self.assertEqual(ScanEta.describe(None), '')
        self.assertEqual(ScanEta.describe(20), 'less than a minute left')
        self.assertEqual(ScanEta.describe(6 * 60), 'about 6 min left')
        self.assertEqual(ScanEta.describe(125 * 60), 'about 2 h 5 min left')


if __name__ == '__main__':
    unittest.main()
