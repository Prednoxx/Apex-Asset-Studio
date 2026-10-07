"""Theme contrast and compatibility."""
import unittest

from apex_asset_studio.ui import appearance, gloss


class ThemeTests(unittest.TestCase):
    def tokens(self, name):
        appearance.ACTIVE['style'] = name
        try: return appearance.tokens(appearance.STYLES[name]['colors'])
        finally: appearance.ACTIVE['style'] = appearance.DEFAULT_STYLE

    def test_text_contrast(self):
        for name in appearance.STYLES:
            t = self.tokens(name)
            with self.subTest(theme=name):
                for surface in ('surface', 'background'):
                    self.assertGreaterEqual(appearance.contrast(t['text'], t[surface]), 7)
                    self.assertGreaterEqual(appearance.contrast(t['muted'], t[surface]), 4.5)
                self.assertGreaterEqual(appearance.contrast(t['selection_text'], t['selection']), 4.5)
                self.assertGreaterEqual(appearance.contrast(t['accent_text'], t['accent']), 3)

    def test_backdrops_render(self):
        for name, spec in appearance.STYLES.items():
            t = self.tokens(name)
            with self.subTest(theme=name):
                image = gloss.backdrop(spec['fx']['backdrop'], (160, 90), t)
                self.assertEqual((image.size, image.mode), ((160, 90), 'RGBA'))
                self.assertEqual(image.getchannel('A').getextrema(), (255, 255))

    def test_old_settings_fall_back(self):
        old = appearance.normalize({'version': 5, 'preset': 'Neon Cybercore', 'base': 'Neon Cybercore', 'text_scale': 1.3})
        self.assertEqual(old['preset'], appearance.DEFAULT_STYLE)
        self.assertEqual(old['text_scale'], 1.3)
        kept = appearance.normalize({'version': 5, 'preset': 'Aero Day', 'base': 'Aero Day'})
        self.assertEqual(kept['preset'], 'Aero Day')

    def test_text_contrast_meets_wcag(self):
        """Normal/high-contrast text meets WCAG."""
        saved = dict(appearance.ACTIVE)
        try:
            for hc in (False, True):
                appearance.ACTIVE['contrast'] = hc; need = 7 if hc else 4.5
                for name, spec in appearance.STYLES.items():
                    appearance.ACTIVE['style'] = name
                    t = appearance.tokens(spec['colors'])
                    pairs = [('text', t['text'], t['surface'], need), ('muted', t['muted'], t['surface'], need),
                             ('muted/background', t['muted'], t['background'], 4.5), ('warn', t['warn'], t['surface'], need),
                             ('button label', t['accent_text'], t['accent_fill'], need),
                             ('selected row', t['selection_text'], t['selection'], 4.5)]
                    pairs += [(rarity, color, t['surface'], need) for rarity, color in appearance.rarity(t).items()]
                    for label, fg, bg, minimum in pairs:
                        with self.subTest(theme=name, high_contrast=hc, pair=label):
                            self.assertGreaterEqual(appearance.contrast(fg, bg), minimum)
        finally:
            appearance.ACTIVE.clear(); appearance.ACTIVE.update(saved)


if __name__ == '__main__':
    unittest.main()
