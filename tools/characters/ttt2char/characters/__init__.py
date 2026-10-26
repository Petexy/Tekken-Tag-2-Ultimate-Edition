"""What to take for each fighter: a module per fighter (asset paths, names and rules, no data), named in CHARACTERS.
They import nothing, so that the launcher's questions (launcher.py) need no numpy.

A fighter comes from Tekken 7 (TEKKEN7_ID, TEKKEN7_CODE, TEKKEN7) or from Tekken 8 (TEKKEN8_ID, TEKKEN8_CODE,
TEKKEN8): game_of() tells which game's files the importer reads it from (source.py)."""
import importlib

from .. import InputError

CHARACTERS = ('kazumi', 'chloe', 'eliza', 'claudio', 'akuma', 'gigas', 'josie', 'katarina', 'master_raven', 'shaheen',
              'fahkumram', 'leroy', 'lidia', 'kunimitsu2', 'negan', 'geese', 'noctis', 'reina')
GAMES = {'tekken7': 'Tekken 7', 'tekken8': 'Tekken 8'}       # (the players' names of the games)


def definition(name):
    if name not in CHARACTERS:
        raise InputError('no fighter "%s" to import; the importer knows: %s' % (name, ', '.join(CHARACTERS)))
    return importlib.import_module('.' + name, __name__)


def game_of(d):
    """'tekken8' for a fighter from Tekken 8 (its definition names its TEKKEN8_CODE), else 'tekken7'."""
    return 'tekken8' if isinstance(getattr(d, 'TEKKEN8_CODE', None), str) else 'tekken7'
