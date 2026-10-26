"""Tekken 8 PC (Unreal Engine 5, project "Polaris"), read-only: the player's own installation as a source of
fighters, next to tekken7/. Nothing of the game is stored in this package; everything is read from the player's
files at import time, and nothing is ever written to them.

The installation and its packages:
    store.py      the installation: IoStore containers (.utoc/.ucas) and pak files, read(path), find(pattern),
                  package(path); patches win
    pak.py        pak files (version 11): Wwise banks and media and other loose files
    oodle.c       the game's own Oodle decompressor, called natively (built by ttt2char/native.py)
    cityhash.py   CityHash64 and the package / script object ids made from it
    zen.py        cooked packages: names, imports, exports, bulk data; names resolved store-wide
    reflect.py    class and struct layouts read from the game's program (cached)
    uprops.py     unversioned properties -> Python values
The model, its materials and the fighter's voice:
    texture.py    cooked textures (UTexture2D): their mips, inline or in the .ubulk, decoded
    mesh.py       cooked skeletal meshes with tekken7.mesh's interface (skeleton, materials, sections, geometry)
    names.py      joint names -> Tekken 7's (convert/skeleton.py's), and how each joint moves when re-posed
    costume.py    a costume (CustomizeSet): which meshes it wears and in which colours
    material.py   material instances and costume colours (the parameters in effect along the instance chain)
    bake.py       materials -> one albedo texture each, and the TTT2 template each becomes
    model.py      a costume's meshes -> one skinned model in TTT2 space (what convert/model.py takes)
    cloth.py      the strands the game simulates (cords, strap ends, ties) -> convert/cloth.py's swinging chains
    skin.py       the fighters both games have, with faces of their own, for convert/skin.py's skin colour gain
    wwise.py      Wwise sound data (bank version 145): one small bank per event, its audio as loose files
    voice.py      a fighter's voice clips by kind, for convert/voice.py
The moveset (the files autodump.py saves):
    autodump.py   the movesets (in tkdata.bin) as the running game's own reader hands them over: Tekken 8 run
                  hidden by dump_tekken8.py and import_character.py (t8helper next to it), the files saved under
                  ~/.local/share/ttt2
    motbin.py     a fighter's moveset (.motbin) -> the common moveset form (movesets.py), in Tekken 8's numbering
    city32.py     CityHash32: the hash the moves and animations are named by
    movenames.py  the moves' names, found on the player's machine (the moveset keeps only their hashes)
    anmbin.py     the animation banks: a fighter's own (.anmbin) and the shared one (com.anmbin)
    panm.py       the banks' animations (PANM) -> per-joint local transforms per frame
    anim.py       body animations retargeted onto a TTT2 skeleton, for the converter's motion pack
    movelist.py   the command list (.mvl, MVLT) -> a TTT2 command list

    from ttt2char.tekken8 import store, uprops
    s = store.Store('/path/to/steamapps/common/TEKKEN 8')
    pkg = s.package('/Game/Character/Item/Customize_Set/zbr/CS_zbr_1p')
    props, end = uprops.read(pkg, pkg.main_export())

Ground rules kept by every module: no keys and no decryption (encrypted containers and entries are refused, the
encrypted moveset archive Polaris/Content/Binary/pak/tkdata.bin is never opened), the game is never started (but
by autodump.py, hidden, for its own reader to read the movesets).
"""
