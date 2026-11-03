"""Turns a fighter from the player's own copy of another Tekken game into a character pack for Tekken Tag
Tournament 2 (this repository's port). Everything is read from the player's files at import time; nothing of
any game is stored in this package.

    ttt2/       the Wii U game's archives and file formats (models, textures, skeletons, item databases,
                movesets, motions)
    tekken7/    Tekken 7 PC: pak files, Unreal Engine 4.14 packages (textures, skeletal meshes, materials) and
                TKMovesets2 moveset files
    convert/    Tekken 7 -> TTT2: skeleton, model, textures, item database, moveset
    characters/ what to take for each fighter (asset paths, names and rules, no data)
    pack.py     writes the pack the port loads (runtime/src/title/roster.cpp)
"""


class InputError(Exception):
    """An input is missing or is not what the importer needs; the message says what to do."""


def _python_packages():
    """numpy and Pillow as the launcher got them for this Python (python_packages.py), when it did: on the path
    before the site-packages folders, where $PYTHONPATH would put them (an old or broken numpy of the system's does
    not hide them). Nothing changes for a Python whose packages the launcher never got."""
    import os
    import sys
    from . import paths
    folder = paths.python_packages()
    if folder and os.path.isdir(folder) and folder not in sys.path:
        site = [i for i, p in enumerate(sys.path) if os.path.basename(p) in ('site-packages', 'dist-packages')]
        sys.path.insert(site[0] if site else len(sys.path), folder)


_python_packages()
