"""Stable native-fighter targets and T7 costume names; contains no game assets.

Append profiles and presets: their positions reserve body/texture namespaces.
Kunimitsu, Slim Bob and Forest Law deliberately have no native costume mapping.
"""
import json
from pathlib import Path
from . import InputError

PROFILES = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
BY_CODE = {p['code']: p for p in PROFILES}
PAUL_LABELS = dict(zip(BY_CODE['pau']['presets'], (
    'Tekken 7 default (1P)', 'Tekken 7 default (2P)', 'Default alternate colour', 'Cowboy',
    'Cowboy alternate colour', 'Cowboy poncho', 'Flame jersey', 'Ninja', 'Biker', 'Silver biker')))

def profile(code='pau'):
    try:
        return BY_CODE[code]
    except KeyError:
        raise InputError('Unsupported native costume target: ' + str(code)) from None

def presets(code='pau'):
    p = profile(code)
    def label(name):
        if code == 'pau': return PAUL_LABELS[name]
        return {'DefaultCos1P': 'Tekken 7 default (1P)', 'DefaultCos2P': 'Tekken 7 default (2P)'}.get(
            name, name.replace('_', ' ').capitalize())
    return [(name, label(name)) for name in p['presets']]

def page_size(code='pau'):
    return 14 - profile(code)['originals'] - 5

def body_code(name, code='pau'):
    p = profile(code)
    n = p['presets'].index(name)
    if code == 'pau': return 'pv' + chr(ord('a') + n)
    n += (p['index'] - 1) * 64
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
    return 'qr'[n // 1296] + alphabet[(n // 36) % 36] + alphabet[n % 36]

def texture_base(code='pau'):
    if code == 'pau': return 0x10e00000
    n = profile(code)['index'] - 1
    # The tested Paul pack owns 0x10e00000..0x10e1ffff.
    if n >= 16: n += 2
    return 0x10d00000 + n * 0x10000

def texture_ids(name, code='pau'):
    p = profile(code)
    n = p['presets'].index(name)
    if code == 'pau': return 0x10e00000 + n * 0x1000, 0x10e10000 + n
    return texture_base(code) + n * 0x400, texture_base(code) + 0xf000 + n

def request(names, remove=False):
    """Launcher arguments; unqualified names retain the original Paul API."""
    if remove:
        code = names[0] if names else 'pau'
        profile(code)
        return code, []
    codes = {n.split(':', 1)[0] for n in names if ':' in n}
    if len(codes) > 1 or (codes and any(':' not in n for n in names)):
        raise InputError('Choose presets for one native fighter at a time.')
    code = next(iter(codes), 'pau')
    profile(code)
    return code, [n.split(':', 1)[-1] for n in names]
