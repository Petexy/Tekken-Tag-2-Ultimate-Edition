import unittest
from unittest.mock import patch
from ttt2char.convert import strips

class NativeStripTests(unittest.TestCase):
    def test_fallback_keeps_winding_and_duplicate_triangles(self):
        triangles = [(0, 1, 2), (0, 1, 2), (3, 5, 4), (6, 6, 7)]
        with patch.object(strips, 'stripify', return_value=[9, 10, 11]):
            result = strips.checked(triangles)
        self.assertTrue(strips.check(triangles, result))
        self.assertEqual(result.count(0xffff), 2)

    def test_fallback_does_not_overflow_the_index_count(self):
        with patch.object(strips, 'stripify', return_value=[]), self.assertRaises(ValueError):
            strips.checked([(0, 1, 2), (3, 4, 5)], limit=6)

    def test_ordinary_sections_keep_the_greedy_strip(self):
        triangles = [(0, 1, 2), (2, 1, 3)]
        self.assertEqual(strips.checked(triangles), strips.stripify(triangles))
