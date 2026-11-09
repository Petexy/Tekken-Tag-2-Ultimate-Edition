"""Unit tests of convert/idlook.py (a definition's costume IDs at given colours) on made-up data."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import idlook          # noqa: E402


def _texture():
    """A 4 x 4 bake: the left half one ID (R channel level 1 of 2), the right half another (level 2), the bottom row
    under a G channel ID on top; its colours a made-up shading."""
    rgb = np.zeros((4, 4, 3), np.float32)
    rgb[:, :2] = (0.10, 0.05, 0.05)
    rgb[0, 0] = (0.20, 0.10, 0.10)                  # (a brighter texel: its share of the mean)
    rgb[:, 2:] = (0.02, 0.02, 0.02)
    idmap = np.zeros((4, 4, 4), np.uint8)
    idmap[:, :2, 0] = 127                           # R, 2 levels: 127 -> level 1 (ID01) at full ramp
    idmap[:, 2:, 0] = 255                           # level 2 (ID02)
    idmap[3, :, 1] = 255                            # G, 1 level: ID05, over both
    return rgb, idmap


class IdLook(unittest.TestCase):
    def test_plain_gain_to_the_mean(self):
        rgb, idmap = _texture()
        out = idlook._apply(rgb, idmap, [2, 1, 0, 0], {1: (0.4, 0.1, 0.1)})
        core = np.zeros((4, 4), bool)
        core[:3, :2] = True
        mean = rgb[core].mean(0)
        np.testing.assert_allclose(out[1, 1], rgb[1, 1] * np.array([0.4, 0.1, 0.1]) / mean, rtol=5e-3)
        np.testing.assert_allclose(out[0, 0] / out[1, 1], [2.0, 2.0, 2.0], rtol=5e-3)    # its shading kept
        np.testing.assert_allclose(out[:, 2:], rgb[:, 2:])                               # other IDs as baked
        np.testing.assert_allclose(out[3], rgb[3])                                       # under a G ID on top: as baked

    def test_contrast_flattens_its_shading(self):
        rgb, idmap = _texture()
        out = idlook._apply(rgb, idmap, [2, 1, 0, 0], {1: (0.4, 0.4, 0.4, 0.5)})
        ratio = out[0, 0] / out[1, 1]
        np.testing.assert_allclose(ratio, [2 ** 0.5] * 3, rtol=5e-3)                     # 2 x as bright -> sqrt(2)

    def test_top_channel_id(self):
        rgb, idmap = _texture()
        out = idlook._apply(rgb, idmap, [2, 1, 0, 0], {5: (0.5, 0.5, 0.5)})
        np.testing.assert_allclose(out[3].mean(0), [0.5, 0.5, 0.5], rtol=1e-5)           # the G ID's row, wherever
        np.testing.assert_allclose(out[:3], rgb[:3])

    def test_no_looks_or_ids_keep_the_bake(self):
        rgb, idmap = _texture()
        np.testing.assert_allclose(idlook._apply(rgb, idmap, [2, 1, 0, 0], {9: (1, 1, 1)}), rgb)

        class NoTextures:
            def exists(self, path):
                return False
        eff = {'textures': {}, 'vectors': {'SplitNumberPerChannel': {'r': 2.0}}}
        self.assertIs(idlook.apply(rgb, eff, NoTextures(), {1: (1, 1, 1)}), rgb)


if __name__ == '__main__':
    unittest.main()
