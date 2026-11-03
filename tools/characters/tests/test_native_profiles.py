"""Roster identity and complete body/texture namespace checks, without game assets."""
import unittest
from ttt2char import InputError, native_costumes as native
from ttt2char.native_profiles import PROFILES, BY_CODE, body_code, texture_ids, page_size, request

class NativeProfileTests(unittest.TestCase):
    def test_targets_preserve_requested_separations(self):
        self.assertEqual(len(PROFILES), 34)
        self.assertTrue({'knm','kmi','sli','flw'}.isdisjoint(BY_CODE))
        self.assertEqual(BY_CODE['law']['id'], 1)
        self.assertEqual(BY_CODE['jac']['id'], 19)
        self.assertEqual(BY_CODE['jul']['id'], 10)
        self.assertEqual(BY_CODE['asa']['id'], 39)
        self.assertEqual(BY_CODE['pan']['id'], 43)

    def test_all_body_codes_and_texture_intervals_are_disjoint(self):
        codes, intervals = set(), []
        for p in PROFILES:
            self.assertLessEqual(len(p['presets']), 60)
            self.assertGreater(page_size(p['code']), 0)
            self.assertEqual(len(native.selection(p['presets'], p['code'])), len(p['presets']))
            for name in p['presets']:
                code = body_code(name, p['code'])
                self.assertNotIn(code, codes)
                self.assertEqual(len(code), 3)
                codes.add(code)
                body, preview = texture_ids(name, p['code'])
                for first, size in ((body, 0x1000 if p['code'] == 'pau' else 0x400), (preview, 1)):
                    self.assertEqual(first >> 24, 0x10)
                    self.assertGreaterEqual(first, 0x10d00000)
                    intervals.append((first, first + size))
        intervals.sort()
        for previous, following in zip(intervals, intervals[1:]):
            self.assertLessEqual(previous[1], following[0])
        self.assertEqual(len(codes), 321)
        self.assertEqual(body_code('cb'), 'pvd')
        self.assertEqual(texture_ids('cb'), (0x10e03000, 0x10e10003))

    def test_request_rejects_cross_target_or_excluded_fighters(self):
        self.assertEqual(request(['law:DefaultCos1P']), ('law', ['DefaultCos1P']))
        self.assertEqual(request(['cb']), ('pau', ['cb']))
        for names in (['law:DefaultCos1P','cb'], ['law:DefaultCos1P','jul:nature'], ['knm:DefaultCos1P']):
            with self.assertRaises(InputError): request(names)

    def test_page_capacity_preserves_native_and_custom_slots(self):
        self.assertEqual(page_size('law'), 5)
        self.assertEqual(page_size('mig'), 4)
        self.assertEqual(page_size('kum'), 7)
        self.assertEqual(page_size('pau'), 6)
