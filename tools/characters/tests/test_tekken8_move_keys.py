"""Unit tests of a definition's Tekken 8 moves named by their key (convert/moveset.py resolve_keys): the same move in
every build of the game, where its index changes when an update adds moves."""
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.characters import CHARACTERS, definition, game_of  # noqa: E402
from ttt2char.convert import moveset  # noqa: E402


class Moves:
    """A Tekken 8 moveset as resolve_keys reads it: the moves' name keys, and the names found for some."""
    def __init__(self, keys, names=None):
        self.tables = {'moves': [{'name_key': k} for k in keys]}
        self.names = names or {}

    def move_name(self, i):
        return self.names.get(i, '')


def fighter(moveset_, prefabs=None):
    d = types.ModuleType('fighter')
    d.NAME = 'Fighter'
    d.MOVESET = moveset_
    if prefabs is not None:
        d.PREFABS = prefabs
    return d


class ResolveKeys(unittest.TestCase):
    def test_a_key_names_the_move_as_this_moveset_does(self):
        d = fighter({'bounds': {'key:000000aa': True, 'Zbr_2RP': True}, 'own_reactions': ('key:000000bb',)},
                    {'held_moves': ('key:000000aa',), 'scene_cuts': {'key:000000aa': (66, 'key:000000bb', 40)}})
        moveset.resolve_keys(d, Moves([0x11, 0xaa, 0xbb], {2: 'Zbr_Named'}))
        self.assertEqual(d.MOVESET, {'bounds': {'#1': True, 'Zbr_2RP': True}, 'own_reactions': ('Zbr_Named',)})
        self.assertEqual(d.PREFABS, {'held_moves': ('#1',), 'scene_cuts': {'#1': (66, 'Zbr_Named', 40)}})

    def test_another_build_from_the_definition_as_written(self):
        d = fighter({'bounds': {'key:000000aa': True}})
        moveset.resolve_keys(d, Moves([0x11, 0xaa]))
        self.assertEqual(d.MOVESET, {'bounds': {'#1': True}})
        moveset.resolve_keys(d, Moves([0x11, 0x22, 0x33, 0xaa]))           # (an update added moves before it)
        self.assertEqual(d.MOVESET, {'bounds': {'#3': True}})

    def test_a_key_in_a_pattern(self):
        d = fighter({'drop_moves': r'^Zbr_Direct$|^(key:000000aa|key:000000bb)$'})
        moveset.resolve_keys(d, Moves([0xbb, 0xaa]))
        pattern = re.compile(d.MOVESET['drop_moves'])
        self.assertEqual([n for n in ('#0', '#1', '#2', 'Zbr_Direct', '#10') if pattern.search(n)],
                         ['#0', '#1', 'Zbr_Direct'])

    def test_a_key_no_move_has(self):
        d = fighter({'bounds': {'key:000000aa': True, 'key:000000cc': True}})
        with self.assertRaisesRegex(ValueError, 'no move of key:000000cc'):
            moveset.resolve_keys(d, Moves([0xaa]))

    def test_nothing_else_changes(self):
        d = fighter({'bounds': {'Zbr_2RP': True}, 'damage': {'Zbr_1': 20}, 'texts': ['a key: b'], 'set': {1, 2}})
        moveset.resolve_keys(d, Moves([0xaa]))
        self.assertEqual(d.MOVESET, {'bounds': {'Zbr_2RP': True}, 'damage': {'Zbr_1': 20}, 'texts': ['a key: b'],
                                     'set': {1, 2}})
        self.assertFalse(hasattr(d, 'PREFABS'))


class Definitions(unittest.TestCase):
    def test_no_tekken8_move_by_its_index(self):
        """A Tekken 8 definition names an unnamed move by its key: its index ('#1495') changes with the game's
        updates."""
        def strings(v):
            if isinstance(v, dict):
                return [s for a, b in v.items() for s in strings(a) + strings(b)]
            if isinstance(v, (list, tuple, set, frozenset)):
                return [s for x in v for s in strings(x)]
            return [v] if isinstance(v, str) else []
        for name in CHARACTERS:
            d = definition(name)
            if game_of(d) != 'tekken8':
                continue
            written = vars(d).get('_KEYED_AS_WRITTEN', {})
            for part in moveset.KEYED:
                found = [s for s in strings(written.get(part, getattr(d, part, None))) if re.search(r'#\d', s)]
                self.assertEqual(found, [], '%s %s' % (name, part))


if __name__ == '__main__':
    unittest.main()
