"""Where an added fighter comes from: the player's own Tekken 7 or Tekken 8, behind one interface.

The TTT2 side of the importer (skeleton fitting, strips, NUD/NUT/BON, the sound banks, the 2D pictures, shared/)
never asks which game a fighter came from: it asks the fighter's source for what it needs, in the vocabulary
Tekken 7's reading has always used (convert/model.py's model dict, tekken7.material's effective parameters,
convert/voice.py's Clips):
    load_model(parts, merge_order, log)   the costume's meshes as one skinned mesh in TTT2 space (mm, Y up)
    materials(), textures()               effective material parameters; decoded textures (exists, get, linear)
    bake_albedo(eff, textures, grey)      a material's linear albedo and alpha, from the game's shader formulas
    classify(name, base, alpha)           the TTT2 template kind of a material (or None: left out)
    material_paths(parts)                 {material name: its object path} of the parts' meshes
    FACE_WORDS                            what a face skin material's name holds (its colour picks the skin gain)
    skin_faces(sex)                       [(TTT2 code, face material path)] of fighters both games have (skin.py)
    NO_COLOURS                            the costume colours of a reference face (none: the material's own)
    picture(path)                         a UI picture as (H, W, 4) uint8 (convert/art.py)
    clips(d)                              the fighter's voice clips by kind (convert/voice.Clips' interface)
    cloth(k, parts, log)                  (Tekken 8) the cloth it simulates as convert/cloth.add takes it
Tekken7Source wraps the paks (tekken7/), Tekken8Source the store (tekken8/). A definition with TEKKEN8_CODE is a
Tekken 8 fighter (characters.game_of); source_of() opens the source a definition needs, and Sources keeps one per
game for shared/, which reads every installed fighter's pictures and name call again (a Tekken 7 and a Tekken 8
fighter side by side need both games).

Tekken 8 is found like Tekken 7, through Steam's files (its app id's manifest in a library), when no folder is
given. This module imports no numpy itself (the launcher asks where the games are): each source loads its readers
when it is made.

Written for this project (no third-party code).
"""
import os
import re

from . import InputError
from .characters import GAMES, game_of

TEKKEN8_APP_ID = 1778820        # Tekken 8's Steam app id (its manifest appmanifest_<id>.acf in a Steam library)
TEKKEN8_FOLDER = 'TEKKEN 8'     # its folder below steamapps/common when the manifest names none


# ------------------------------------------------------------------------------------------------ Tekken 7
class Tekken7Source:
    """The player's Tekken 7: its paks (tekken7.pak.Paks)."""

    game = 'tekken7'
    NAME = GAMES['tekken7']
    FACE_WORDS = ('skin_face',)                  # MI_CH_kzm_skin_face
    NO_COLOURS = {}

    def __init__(self, paks):
        self.paks = paks

    def __repr__(self):
        return '<Tekken 7 source %r>' % (self.paks,)

    def load_model(self, parts, merge_order, log=None):
        from .convert import model
        return model.load_tekken7_model(self.paks, parts, merge_order)

    def mesh(self, path):
        from .tekken7 import mesh
        from .tekken7.uasset import load
        return mesh.SkeletalMesh(load(self.paks, path))

    def materials(self):
        from .tekken7.material import Materials
        return Materials(self.paks)

    def textures(self):
        from .convert import model
        return model.Textures(self.paks)

    @staticmethod
    def bake_albedo(eff, textures, grey=False):
        from .convert import model
        return model.bake_albedo(eff, textures, grey=grey)

    @staticmethod
    def classify(name, base, alpha):
        from .convert import model
        return model.classify(name, base, alpha)

    def material_paths(self, parts):
        """{material instance name: its object path ('/Game/a/b.b')} of the parts' skeletal meshes, the first mesh
        naming one first."""
        from .tekken7.material import short_ref
        out = {}
        for _, path in parts:
            for x in self.mesh(path).materials:
                if x['material']:
                    ref = short_ref(x['material'])
                    out.setdefault(ref.split('.')[-1], ref)
        return out

    def skin_faces(self, sex):
        from .convert import skin
        return skin.tekken7_faces(self.paks, sex)

    def picture(self, path):
        from .tekken7.texture import Texture2D
        from .tekken7.uasset import load
        return Texture2D(load(self.paks, path)).decode()

    def clips(self, d):
        from .convert import voice
        return voice.Clips(self.paks, d.TEKKEN7_CODE, d.VOICE_PREFIX)


# ------------------------------------------------------------------------------------------------ Tekken 8
class Tekken8Source:
    """The player's Tekken 8: its store (tekken8.store.Store) through the Tekken 8 adapters (tekken8/: meshes,
    materials, costumes, pictures and voice with Tekken 7's interfaces)."""

    game = 'tekken8'
    NAME = GAMES['tekken8']
    FACE_WORDS = ('face_skin',)                  # MI_CH_zbr_face_skin
    NO_COLOURS = None

    def __init__(self, store):
        self.store = store

    def __repr__(self):
        return '<Tekken 8 source %r>' % (self.store,)

    def costume(self, d, which):
        """tekken8.costume.costume of the fighter's costume `which` ('1p', '2p' or a CustomizeSet path): {'parts':
        [(tag, mesh path)], 'merge_order', 'colours', 'set'}."""
        from .tekken8 import costume
        return costume.costume(self.store, d.TEKKEN8_CODE, which)

    def load_model(self, parts, merge_order, log=print):
        from .tekken8 import model
        return model.load_model(self.store, parts, merge_order, log=log)

    @staticmethod
    def cloth(k, parts, log=print):
        """The strands of the costume Tekken 8 simulates (tekken8/cloth.py), as convert/cloth.find gives Tekken 7's
        cloth: k the model as model.tekken8_model makes it, parts [(tag, path)]."""
        from .tekken8 import cloth
        return cloth.find(k, parts, log=log)

    def mesh(self, path):
        from .tekken8 import mesh
        return mesh.SkeletalMesh(self.store, path)

    def materials(self):
        from .tekken8 import material
        return material.Materials(self.store)

    def textures(self):
        from .tekken8 import material
        return material.Textures(self.store)

    @staticmethod
    def bake_albedo(eff, textures, grey=False):
        from .tekken8 import bake
        return bake.bake_albedo(eff, textures, grey=grey)

    @staticmethod
    def classify(name, base, alpha):
        from .tekken8 import bake
        return bake.classify(name, base, alpha)

    def material_paths(self, parts):
        """{material instance name: its object path} of the parts' skeletal meshes (the first naming one first)."""
        out = {}
        for _, path in parts:
            for x in self.mesh(path).materials:
                if x.get('material'):
                    out.setdefault(material_name(x['material']), x['material'])
        return out

    def skin_faces(self, sex):
        """The Tekken 8 face materials of fighters TTT2 has too, of that sex (skin.WOMEN: TTT2's women)."""
        from .convert import skin
        from .tekken8 import skin as skin8
        women = sex == 'female'
        return [(code, path) for code, path in skin8.reference_faces()
                if (code in skin.WOMEN) == women and self.store.exists(path)]

    def picture(self, path):
        from .tekken8 import texture
        return texture.Texture2D(self.store, path).decode()

    def clips(self, d):
        from .tekken8 import voice
        return voice.Clips(self.store, getattr(d, 'VOICE', d.TEKKEN8_CODE))


def material_name(path):
    """A material's name in the model dict: its object's name ('/Game/a/MI_x.MI_x' or '/Game/a/MI_x' -> 'MI_x')."""
    return path.rsplit('/', 1)[-1].split('.')[-1].split(':')[0]


# ------------------------------------------------------------------------------------------------ opening
def of(source):
    """`source` as a source: a Tekken 7 Paks (what the Tekken 7 steps took before sources: outfits.py's preset
    bodies) becomes a Tekken7Source."""
    return source if hasattr(source, 'game') and hasattr(source, 'load_model') else Tekken7Source(source)


def steam_libraries():
    """The Steam library folders of every Steam installed (as tekken7.autodump finds Tekken 7's), once each."""
    from .tekken7 import autodump
    return list(dict.fromkeys(lib for steam, sandbox in autodump.steams()
                              for lib in autodump._libraries(steam, sandbox)))


def find_tekken8():
    """Tekken 8's installation folder through Steam's files (its app manifest in a library), or None."""
    for lib in steam_libraries():
        acf = os.path.join(lib, 'steamapps', 'appmanifest_%d.acf' % TEKKEN8_APP_ID)
        if not os.path.isfile(acf):
            continue
        with open(acf, encoding='utf-8', errors='replace') as f:
            m = re.search(r'"installdir"\s+"([^"]+)"', f.read())
        folder = os.path.join(lib, 'steamapps', 'common', m.group(1) if m else TEKKEN8_FOLDER)
        if os.path.isdir(folder):
            return folder
    return None


def tekken8_folder(folder):
    """The Tekken 8 installation to read: `folder` (checked: tekken8.store.game_folder), else the one Steam has.
    InputError when there is none."""
    if not folder:
        folder = find_tekken8()
        if folder is None:
            raise InputError('Tekken 8 is not installed in any Steam library: give --tekken8, your Tekken 8 PC '
                             'installation (the \'%s\' folder: in Steam, right-click Tekken 8 > Manage > Browse local '
                             'files)' % TEKKEN8_FOLDER)
    from .tekken8 import store
    return store.game_folder(folder)


def open_tekken8(folder):
    """A Tekken8Source of the installation in `folder` (tekken8_folder)."""
    from .tekken8 import store
    try:
        return Tekken8Source(store.Store(tekken8_folder(folder)))
    except (OSError, ValueError) as error:
        raise InputError('cannot read Tekken 8\'s files in %s (%s): verify the integrity of Tekken 8\'s files in '
                         'Steam' % (folder, error))


def open_tekken7(folder, files=None):
    """A Tekken7Source of the installation in `folder` (the folder holding TekkenGame/); files: the folder of the
    files Tekken 7 keeps encrypted, as the game reads them (tekken7/autodump.py saves them)."""
    from .tekken7.autodump import FILES
    from .tekken7.pak import Paks, pak_names
    paks = os.path.join(folder or '', 'TekkenGame', 'Content', 'Paks')
    if not folder or not pak_names(paks):
        raise InputError('--tekken7 must be your own Tekken 7 PC installation, the folder holding TekkenGame/ '
                         '(Steam: Library > Tekken 7 > Manage > Browse local files); found no pak files in %s' % paks)
    try:
        return Tekken7Source(Paks(paks, saved=files if files is not None else FILES))
    except (OSError, ValueError) as error:
        raise InputError('cannot read the pak files in %s (%s): let Steam verify Tekken 7\'s files' % (paks, error))


def source_of(d, tekken7_dir=None, tekken8_dir=None, files=None):
    """The source fighter d is read from (its game's: characters.game_of), opened from that game's folder."""
    if game_of(d) == 'tekken8':
        return open_tekken8(tekken8_dir)
    if not tekken7_dir:
        raise InputError('%s comes from Tekken 7: give --tekken7, your Tekken 7 PC installation' % d.NAME)
    return open_tekken7(tekken7_dir, files)


class Sources:
    """One source per game, opened when a fighter of that game first needs one (shared/ reads every installed
    fighter's pictures and name call again). opened: sources already open (the import's own)."""

    def __init__(self, tekken7=None, tekken8=None, files=None, opened=()):
        self.folders = {'tekken7': tekken7, 'tekken8': tekken8}
        self.files = files
        self.opened = {s.game: s for s in opened}

    def __call__(self, d):
        game = game_of(d)
        if game not in self.opened:
            if game == 'tekken7' and not self.folders['tekken7']:
                raise InputError('%s\'s pack is installed: what the packs share is made again from every added '
                                 'fighter\'s own game, and %s comes from Tekken 7: give --tekken7 (or remove that '
                                 'pack)' % (d.NAME, d.NAME))
            self.opened[game] = source_of(d, self.folders['tekken7'], self.folders['tekken8'], self.files)
        return self.opened[game]

    def games(self):
        """The games of the sources open now."""
        return sorted(self.opened)
