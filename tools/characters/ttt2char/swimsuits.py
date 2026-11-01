"""Recover native swimwear from an EU v16 Wii U install, without other games.

Packs live in swimsuits/, independently of native/ Tekken 7 costume imports.
The catalog contains identifiers only; every asset is read from the user's game.
"""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from . import InputError, signals
from .ttt2 import bxml

PROFILES = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
BY_CODE = {p['code']: p for p in PROFILES}
DEFAULT = 'デフォルトコスチューム'
UPPER, LOWER, HEAD = '上半身(胴体)', '下半身', '頭'
PREVIEW_BASE = 0x10FC1000  # Outside native T7 body/preview reservations through 0x10F2FFFF.


def body_code(profile, index):
    number = profile['id'] * 4 + index
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
    return 's' + alphabet[number // 36] + alphabet[number % 36]


def data_of(instance):
    return next((dict(c['attrs']) for c in instance['children'] if c['tag'] == 'Data'), {})


def recipe(database, label, cap=None):
    """Keep native equipment IDs/effects, substituting the selected clothing recipe."""
    roots = bxml.parse(database)
    info = roots[0]
    selected = next((i for i in info['children'] if dict(i['attrs']).get('label') == label), None)
    if selected is None:
        raise InputError('Missing swimwear definition: ' + label)
    position = data_of(selected).get('EquipPos')
    target_position = HEAD if position == HEAD else UPPER
    full_body = position == '上半身下半身'
    instances, replaced = [], 0
    for original in info['children']:
        data = data_of(original)
        if data.get('EquipType') != DEFAULT:
            continue
        inst = copy.deepcopy(original)
        pos = data.get('EquipPos')
        if pos == target_position or (full_body and pos == LOWER):
            inst['children'] = [c for c in inst['children'] if c['tag'] not in ('Model', 'ModelBConditions')]
            if pos == target_position:
                inst['children'] += copy.deepcopy([c for c in selected['children'] if c['tag'] in ('Model', 'ModelBConditions')])
                replaced += 1
            else:
                inst['children'].append(dict(tag='Model', attrs=[('section', 'A')], children=[]))
        instances.append(inst)
    if replaced != 1:
        raise InputError('Swimwear needs exactly one native equipment slot: ' + label)
    if cap:
        hat = next(i for i in info['children'] if dict(i['attrs']).get('label') == cap)
        # Combot's original head entry is makeup; append the cap to that recipe.
        head = next(i for i in instances if '_hed_' in dict(i['attrs']).get('label', ''))
        model = next((c for c in head['children'] if c['tag'] == 'Model' and dict(c['attrs']).get('section') == 'A'), None)
        if model is None:
            model = dict(tag='Model', attrs=[('section', 'A')], children=[])
            head['children'].append(model)
        for part in hat['children']:
            if part['tag'] == 'Model' and dict(part['attrs']).get('section') == 'A':
                model['children'] += copy.deepcopy(part['children'])
    info['children'] = instances
    return bxml.write(roots), selected


def validate_parts(archives, profile, instance):
    """Resolve all character-local resources, including texture/spring index zero."""
    from .ttt2.archive import member_key
    checked = []
    fields = {'mi': (7, b'NDP3'), 'ti': (8, b'NTP3'), 'ni': (8, b'NTP3'),
              'bi': (9, b'BONE'), 'pi': (11, None)}
    for model in instance['children']:
        if model['tag'] != 'Model':
            continue
        for group in model['children']:
            if group['tag'] != 'Group':
                continue
            for field, (kind, magic) in fields.items():
                value = dict(group['attrs']).get(field)
                if value is None:
                    continue
                key = member_key(profile['parts'][str(kind)], int(value))
                if not archives.has(key):
                    raise InputError('Missing %s %s=%s (%08x)' % (profile['code'], field, value, key))
                contents = archives.read(key)
                if magic and contents[:4] != magic:
                    raise InputError('Unexpected asset format: %s %s=%s' % (profile['code'], field, value))
                checked.append(dict(field=field, index=int(value), key='%08x' % key, size=len(contents)))
    return checked


def installed(folder):
    return [p['code'] for p in PROFILES if (Path(folder) / 'swimsuits' / p['code'] / 'native.ini').is_file()]


def _publish(temporary, target):
    backup = target.with_name('.' + target.name + '-backup-' + uuid.uuid4().hex)
    if target.is_symlink() or temporary.is_symlink() or temporary.resolve().parent != target.resolve().parent:
        raise InputError('Swimsuit packs must be ordinary directories.')
    if target.exists():
        if not (target / 'native.ini').is_file():
            raise InputError('Unrecognised swimsuit directory: ' + str(target))
    with signals.deferred():
        if target.exists():
            target.rename(backup)
        try:
            temporary.rename(target)
        except BaseException:
            if backup.exists():
                backup.rename(target)
            raise


def remove(folder, names):
    for code in names:
        if code not in BY_CODE:
            raise InputError('Unsupported swimsuit target: ' + code)
        target = Path(folder) / 'swimsuits' / code
        if target.is_symlink():
            raise InputError('Swimsuit pack must not be a link.')
        if (target / 'native.ini').is_file():
            target.rename(target.with_name('.' + code + '-backup-' + uuid.uuid4().hex))


def build(game, folder, names=None, log=print):
    from .ttt2 import nut
    from .ttt2.archive import Archives, key_of
    from .ttt2.rpx import Rpx
    names = names or [p['code'] for p in PROFILES]
    if set(names) - BY_CODE.keys():
        raise InputError('Unsupported swimsuit target.')
    profiles = [p for p in PROFILES if p['code'] in names]
    out = Path(folder) / 'swimsuits'
    out.mkdir(parents=True, exist_ok=True)
    archives, rpx = Archives(game), Rpx.of_game(game)
    report = []
    try:
        for number, profile in enumerate(profiles):
            code, fighter = profile['code'], profile['id']
            log('@step fighter %s %d %d' % (code, number + 1, len(profiles)))
            actual = rpx.read(rpx.u32(0x107C57F4 + 4 * fighter), 8).split(b'\0')[0].decode()
            if actual != code or rpx.u32(0x103B4B88 + 8 * fighter) != profile['originals'] or profile['parts']['6'] != key_of(code + '.xml'):
                raise InputError('Swimwear requires the supported European Wii U update v16: ' + code)
            database = archives.read_name(code + '.xml')
            files, codes, checked = {}, [], []
            preview = nut.read(archives.read(profile['preview']))
            preview['textures'] = preview['textures'][:profile['originals']]
            if len(preview['textures']) != profile['originals']:
                raise InputError('Incomplete native costume previews: ' + code)
            for index, label in enumerate(profile['items']):
                body = body_code(profile, index)
                xml, item = recipe(database, label, 'cbt_hed_dlc_swimcap' if code == 'cbt' else None)
                checked += validate_parts(archives, profile, item)
                if code == 'cbt':
                    cap = next(i for i in bxml.parse(database)[0]['children'] if dict(i['attrs']).get('label') == 'cbt_hed_dlc_swimcap')
                    checked += validate_parts(archives, profile, cap)
                codes.append(body)
                files[body + '.xml'] = xml
                for suffix in ('.nud', '.nut', '.bon', '.mop', '.havok.xml'):
                    if archives.has(key_of(code + suffix)):
                        files[body + suffix] = archives.read_name(code + suffix)
                    elif suffix == '.mop':
                        from .convert.chains import empty_spring_file
                        files[body + suffix] = empty_spring_file(archives.read_name('lil.mop'))
                    elif suffix != '.havok.xml':
                        raise InputError('Missing native body file: ' + code + suffix)
                # Existing costume previews remain intact; recovered entries use a placeholder.
                image = copy.deepcopy(preview['textures'][0])
                image['gidx'] = PREVIEW_BASE + fighter * 4 + index
                preview['textures'].append(image)
            files['art/costumes.nut'] = nut.write(preview)
            files['native.ini'] = ('format = 1\ntarget = %s\noutfits = %s\nsource = wiiu-swimsuits\n' % (code, ','.join(codes))).encode()
            registry = ['part.%s = %08x' % (kind, key) for kind, key in profile['parts'].items() if kind != '6']
            registry += ['texture.%s = %08x' % (i, key) for i, key in profile['textures'].items()]
            files['registry.ini'] = ('\n'.join(registry) + '\n').encode()
            metadata = dict(format=1, source='wiiu-swimsuits', presets=profile['items'], codes=codes,
                            preview_fallback=True, validated_parts=checked)
            files['presets.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
            temporary = Path(tempfile.mkdtemp(prefix='.' + code + '-import-', dir=out))
            try:
                for name, data in files.items():
                    path = temporary / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                _publish(temporary, out / code)
            except BaseException:
                if temporary.exists() and temporary.resolve().parent == out.resolve() and not temporary.is_symlink():
                    shutil.rmtree(temporary)
                raise
            log(profile['name'] + ': ' + str(len(codes)) + ' swimwear preset(s) installed')
            report.append(dict(code=code, name=profile['name'], presets=len(codes), assets=len(checked)))
    finally:
        archives.close()
    return report
